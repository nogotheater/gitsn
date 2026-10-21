"""Authorized atomic writes for planning-team forms."""
from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import transaction
from delivery.models import (
    Customer, Organization, Contract, ContractProduct, ContractSite, InstallationSite,
    SitePresentation, SiteProductSelection, Product, DisplayKind,
)
from .access import require_manager
from .presentations import initial_partner_visibility


def _check_revision(obj, revision):
    if not revision or revision != obj.updated_at.isoformat():
        raise ValidationError('다른 작업에서 내용이 수정되었습니다. 새로고침해 최신 내용을 확인한 뒤 다시 저장해 주세요.')


def _organization(name):
    matches = list(Organization.objects.select_for_update().filter(official_name__iexact=name)[:2])
    if len(matches) > 1:
        raise ValidationError('같은 명칭의 기관이 여러 곳 등록되어 있습니다. 등록된 기관을 직접 선택해 주세요.')
    return matches[0] if matches else Organization.objects.create(official_name=name)


def _settings(obj, data, *, fallback_category=None, fallback_region=''):
    previous = obj.category
    category = data.get('category') or previous or fallback_category
    if not category:
        raise ValidationError('고객 분류를 선택해 주세요.')
    obj.category = category
    obj.region = data.get('region') or (obj.region if previous else fallback_region)
    # Clear optional region deliberately on a full customer/place edit.
    if fallback_category is None:
        obj.region = data.get('region', '')
    obj.show_in_list = bool(data.get('show_in_list'))
    obj.include_in_total = bool(data.get('include_in_total'))
    obj.display_as = data.get('display_as') or obj.display_as
    policy = data.get('partner_public') or 'default'
    obj.partner_public = (initial_partner_visibility(category)
                          if (previous and previous != category) or policy == 'default'
                          else policy == 'public')
    if 'memo' in data:
        obj.memo = data['memo']


def _retire_logo(storage, name):
    if name and not Customer.objects.filter(logo=name).exists() and not SitePresentation.objects.filter(logo=name).exists():
        storage.delete(name)


def save_presentation(user, data, *, customer_id=None, site_id=None, extra_name_exclusions=()):
    require_manager(user)
    obj = None
    uploaded = data.get('logo')
    previous_logo = ''
    try:
        with transaction.atomic():
            if site_id:
                site = InstallationSite.objects.select_for_update().get(pk=site_id)
                obj = SitePresentation.objects.select_for_update().filter(site=site).first()
                if obj is not None:
                    _check_revision(obj, data.get('revision'))
                else:
                    obj = SitePresentation(site=site)
                owner = site
            elif customer_id:
                obj = Customer.objects.select_for_update().select_related('organization').get(pk=customer_id)
                _check_revision(obj, data.get('revision'))
                owner = obj.organization
            else:
                owner = None
            name = data['official_name']
            if not site_id:
                duplicates = Customer.objects.filter(organization__official_name__iexact=name)
                if customer_id:
                    duplicates = duplicates.exclude(pk=customer_id)
                if extra_name_exclusions:
                    duplicates = duplicates.exclude(pk__in=extra_name_exclusions)
                if duplicates.exists():
                    raise ValidationError({'official_name': '같은 공식 명칭의 고객사가 있습니다. 기존 고객사를 검색해 선택해 주세요.'})
            if owner is None:
                owner = _organization(name)
                obj = Customer(organization=owner)
            else:
                owner.official_name = name
                owner.full_clean()
                owner.save()
            previous_logo = obj.logo.name
            _settings(obj, data)
            if uploaded:
                extension = '.png' if uploaded.image.format == 'PNG' else '.jpg'
                uploaded.name = uuid4().hex + extension
                obj.logo = uploaded
            elif data.get('remove_logo'):
                obj.logo = ''
            obj.full_clean()
            obj.save()
            if previous_logo and previous_logo != obj.logo.name:
                transaction.on_commit(lambda storage=obj.logo.storage, name=previous_logo: _retire_logo(storage, name))
            return obj
    except Exception:
        if uploaded and obj is not None and obj.logo.name != previous_logo and obj.logo._committed:
            obj.logo.storage.delete(obj.logo.name)
        raise


def save_contract(user, customer_id, data, product_rows, site_rows, *, contract_id=None):
    require_manager(user)
    if not product_rows:
        raise ValidationError('제품을 한 개 이상 입력해 주세요.')
    product_ids = [row['product'].pk for row in product_rows]
    if len(set(product_ids)) != len(product_ids):
        raise ValidationError('같은 제품은 한 줄에 수량을 합쳐 입력해 주세요.')
    for row in site_rows:
        if not row['products']:
            raise ValidationError('설치 장소별 실제 제품을 선택해 주세요.')
        if not set(p.pk for p in row['products']).issubset(product_ids):
            raise ValidationError('설치 장소의 제품은 이 계약에 등록한 제품 중에서 선택해 주세요.')
    with transaction.atomic():
        customer = Customer.objects.select_for_update().select_related('organization').get(pk=customer_id)
        if contract_id:
            contract = Contract.objects.select_for_update().get(pk=contract_id, customer=customer)
            _check_revision(contract, data.get('revision'))
        else:
            contract = Contract(customer=customer)
        mode = data['party_mode']
        contract.contracting_party = (customer.organization if mode == 'customer' else
                                     data['contracting_party'] if mode == 'existing' else
                                     _organization(data['new_party_name']))
        for field in ['contract_date', 'is_active', 'source_email_subject', 'source_email_received_on', 'source_email_sender']:
            setattr(contract, field, data[field])
        contract.full_clean()
        contract.save()
        old_lines = {line.product_id: line for line in contract.product_lines.all()}
        lines = {}
        for row in product_rows:
            line = old_lines.get(row['product'].pk) or ContractProduct(contract=contract, product=row['product'])
            line.quantity = row['quantity']
            line.full_clean()
            line.save()
            lines[row['product'].pk] = line
        existing_ids = [row['existing_site'].pk for row in site_rows if row.get('existing_site')]
        presentations = {p.site_id: p for p in SitePresentation.objects.select_for_update().filter(site_id__in=existing_ids).order_by('site_id')}
        # Parent contract lock serializes edits. Rebuild only its relation records.
        SiteProductSelection.objects.filter(contract_site__contract=contract).delete()
        wanted_sites = set()
        for row in site_rows:
            site = row.get('existing_site') or InstallationSite.objects.create(official_name=row['new_site_name'])
            if site.pk in wanted_sites:
                raise ValidationError('같은 설치 장소는 한 번만 연결해 주세요.')
            wanted_sites.add(site.pk)
            link, _ = ContractSite.objects.get_or_create(contract=contract, site=site)
            for product in row['products']:
                SiteProductSelection.objects.create(contract_site=link, contract_product=lines[product.pk])
            presentation = presentations.get(site.pk)
            if presentation is None or row.get('update_display'):
                if presentation is not None:
                    _check_revision(presentation, row.get('display_revision'))
                presentation = presentation or SitePresentation(site=site)
                _settings(presentation, row, fallback_category=customer.category, fallback_region=customer.region)
                presentation.full_clean()
                presentation.save()
        contract.site_links.exclude(site_id__in=wanted_sites).delete()
        contract.product_lines.exclude(product_id__in=product_ids).delete()
        return contract


def end_contract(user, contract_id, revision):
    require_manager(user)
    with transaction.atomic():
        contract = Contract.objects.select_for_update().get(pk=contract_id)
        _check_revision(contract, revision)
        contract.is_active = False
        contract.save()
        return contract


def save_product(user, data, *, product_id=None):
    require_manager(user)
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id) if product_id else Product()
        if product_id:
            _check_revision(product, data.get('revision'))
        for key in ['code', 'name', 'marker', 'color']:
            setattr(product, key, data[key])
        product.full_clean()
        product.save()
        return product


def delete_product(user, product_id):
    require_manager(user)
    with transaction.atomic():
        product = Product.objects.select_for_update().get(pk=product_id)
        used_in = product.contract_lines.count()
        if used_in:
            raise ValidationError(f'"{product.name}"은(는) 계약 {used_in}건에서 쓰이고 있어 삭제할 수 없습니다. 먼저 해당 계약에서 제품을 빼 주세요.')
        product.delete()
        return product
