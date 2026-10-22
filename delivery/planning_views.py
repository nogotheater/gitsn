from functools import wraps
from io import BytesIO
from urllib.parse import urlencode
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.db.models import Prefetch
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from .forms import PresentationForm, ContractForm, ProductFormSet, SiteFormSet, ProductCatalogForm, DuplicateSearchForm, DuplicateContractFormSet
from .domain.products import ordered_products, product_sort_key
from .models import Customer, Contract, Category, DisplayKind, SitePresentation, InstallationSite, Product
from .services.access import require_manager
from .services.logo_cache import logo_bytes
from .services.planning import save_presentation, save_contract, end_contract, save_product, delete_product
from .services.current_performance import customer_current_quantities
from .services.duplicates import duplicate_candidates, merge_duplicate_customers
from .services.customer_location import LOCATION_CATEGORIES, location_data, split_location, suggestion
from .services.customer_delete import deletion_plan, delete_customer
from .domain.locations import format_location


def planning_only(view):
    @wraps(view)
    @login_required
    @never_cache
    def wrapped(request, *args, **kwargs):
        require_manager(request.user)
        return view(request, *args, **kwargs)
    return wrapped


def attach_errors(form, error):
    if isinstance(error, ValidationError):
        if hasattr(error, 'message_dict'):
            for key, errors in error.message_dict.items():
                for message in errors:
                    form.add_error(key if key in form.fields else None, message)
        else:
            for message in error.messages:
                form.add_error(None, message)
    else:
        form.add_error(None, '저장하지 못했습니다. 입력 내용과 최신 자료를 확인한 뒤 다시 저장해 주세요.')


@planning_only
def customer_list(request):
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    rows = Customer.objects.select_related('organization').filter(merged_into__isnull=True).prefetch_related(
        Prefetch('contracts', queryset=Contract.objects.filter(is_active=True).prefetch_related('product_lines__product'), to_attr='current_contracts')
    ).order_by('organization__official_name')
    if query:
        rows = rows.filter(organization__official_name__icontains=query)
    if category in Category.values:
        rows = rows.filter(category=category)
    page = Paginator(rows, 24).get_page(request.GET.get('page'))
    for customer in page:
        badges = {line.product_id: line.product for contract in customer.current_contracts for line in contract.product_lines.all()}
        customer.product_badges = sorted(badges.values(), key=lambda product: product.name)
        customer.needs_location = customer.category in LOCATION_CATEGORIES and not customer.location_code
    return render(request, 'planning/customer_list.html', {'page': page, 'query': query, 'selected_category': category, 'categories': Category.choices})


def presentation_initial(obj, name):
    return {**{field: getattr(obj, field) for field in ['category', 'region', 'include_in_total', 'show_in_list', 'display_as', 'memo']},
            'official_name': name, 'partner_public': 'public' if obj.partner_public else 'private',
            'revision': obj.updated_at.isoformat()}


@planning_only
@require_http_methods(['GET', 'POST'])
def customer_edit(request, customer_id=None):
    customer = get_object_or_404(Customer.objects.select_related('organization'), pk=customer_id) if customer_id else None
    if customer and customer.merged_into_id:
        messages.error(request, '이미 통합된 고객사입니다. 유지된 고객사에서 수정해 주세요.')
        return redirect('planning-customer-detail', customer_id=customer.merged_into_id)
    initial = presentation_initial(customer, str(customer)) if customer else {'display_as': DisplayKind.CUSTOMER, 'official_name': request.GET.get('name', '')}
    if customer:
        sido, unit = split_location(customer.location_code)
        initial.update({'location_sido': sido, 'location_unit': unit, 'institution_type': customer.institution_type})
    form = PresentationForm(request.POST if request.method == 'POST' else None, request.FILES or None, initial=initial, with_location=True)
    if request.method == 'POST' and form.is_valid():
        try:
            saved = save_presentation(request.user, form.cleaned_data, customer_id=customer_id)
        except (ValidationError, DatabaseError) as error:
            attach_errors(form, error)
        else:
            messages.success(request, '고객사 정보를 저장했습니다.')
            return redirect('planning-customer-detail', customer_id=saved.pk)
    return render(request, 'planning/presentation_form.html', {'form': form, 'customer': customer, 'presentation': customer, 'is_site': False,
                                                               'location_data': location_data()})


@planning_only
def customer_detail(request, customer_id):
    customer = get_object_or_404(Customer.objects.select_related('organization', 'merged_into__organization'), pk=customer_id)
    quantities = customer_current_quantities(customer.pk)
    products = Product.objects.in_bulk(quantities.keys())
    # in_bulk uses UUID keys; construct the display map explicitly.
    names = {str(product.pk): product for product in products.values()}
    totals = sorted(((names[key], quantity) for key, quantity in quantities.items()), key=lambda row: product_sort_key(row[0].marker, row[0].name, row[0].pk))
    contracts = customer.contracts.select_related('contracting_party', 'superseded_by__customer__organization').prefetch_related('product_lines__product', 'site_links__site').order_by('-created_at')
    merged_duplicates = customer.merged_duplicates.select_related('organization').order_by('-merged_at')
    return render(request, 'planning/customer_detail.html', {'customer': customer, 'contracts': contracts, 'totals': totals,
                                                             'total_quantity': sum(quantities.values()), 'merged_duplicates': merged_duplicates,
                                                             'location_applies': customer.category in LOCATION_CATEGORIES,
                                                             'location_label': format_location(customer.location_code)})


@planning_only
@require_http_methods(['GET', 'POST'])
def customer_delete(request, customer_id):
    """고객사 삭제(2026-10-22 형우): 계약이 있어도 지운다. GET은 확인 화면, POST가 삭제."""
    customer = get_object_or_404(Customer.objects.select_related('organization'), pk=customer_id)
    if request.method == 'POST':
        try:
            result = delete_customer(request.user, customer.pk)
        except ValidationError as failure:
            messages.error(request, ' '.join(failure.messages))
        except DatabaseError:
            messages.error(request, '고객사를 삭제하지 못했습니다. 잠시 후 다시 시도해 주세요.')
        else:
            messages.success(request, f'"{result["name"]}" 고객사를 삭제했습니다.')
            return redirect('planning-home')
        return redirect('planning-customer-detail', customer_id=customer.pk)
    return render(request, 'planning/customer_delete.html', {'customer': customer, 'plan': deletion_plan(customer)})


@planning_only
@require_GET
def location_guess(request):
    """고객사 화면의 소재지 제안(4단계). 관리자 전용, 읽기만 한다."""
    return JsonResponse(suggestion(request.GET.get('name', ''), request.GET.get('category', ''), request.GET.get('region', '')))


def contract_initial(contract, customer):
    if not contract:
        return {'party_mode': 'customer', 'is_active': 'active'}
    return {**{field: getattr(contract, field) for field in ['contracting_party', 'contract_date', 'source_email_subject', 'source_email_received_on', 'source_email_sender']},
            'party_mode': 'customer' if contract.contracting_party_id == customer.organization_id else 'existing',
            'is_active': 'active' if contract.is_active else 'ended', 'revision': contract.updated_at.isoformat()}


@planning_only
@require_http_methods(['GET', 'POST'])
def contract_edit(request, customer_id, contract_id=None):
    customer = get_object_or_404(Customer.objects.select_related('organization'), pk=customer_id)
    if customer.merged_into_id:
        messages.error(request, '이미 통합된 고객사입니다. 유지된 고객사에서 계약을 등록·수정해 주세요.')
        return redirect('planning-customer-detail', customer_id=customer.merged_into_id)
    contract = get_object_or_404(Contract, pk=contract_id, customer=customer) if contract_id else None
    initial_products = [{'product': line.product_id, 'quantity': line.quantity} for line in contract.product_lines.all()] if contract else []
    presentations = {p.site_id: p for p in SitePresentation.objects.select_related('site').all()}
    initial_sites = []
    if contract:
        for link in contract.site_links.prefetch_related('product_selections__contract_product').all():
            p = presentations.get(link.site_id)
            data = {'existing_site': link.site_id, 'products': [selection.contract_product.product_id for selection in link.product_selections.all()]}
            if p:
                data.update({key: getattr(p, key) for key in ['show_in_list', 'include_in_total', 'display_as', 'category', 'region']})
                data.update(partner_public='public' if p.partner_public else 'private', display_revision=p.updated_at.isoformat())
            initial_sites.append(data)
    post = request.POST if request.method == 'POST' else None
    form = ContractForm(post, initial=contract_initial(contract, customer))
    products = ProductFormSet(post, prefix='products', initial=initial_products)
    sites = SiteFormSet(post, prefix='sites', initial=initial_sites)
    if request.method == 'POST':
        valid = [form.is_valid(), products.is_valid(), sites.is_valid()]
        if all(valid):
            rows = lambda formset: [f.cleaned_data for f in formset if f.cleaned_data and not f.cleaned_data.get('DELETE')]
            try:
                saved = save_contract(request.user, customer.pk, form.cleaned_data, rows(products), rows(sites), contract_id=contract_id)
            except (ValidationError, DatabaseError) as error:
                attach_errors(form, error)
            else:
                messages.success(request, '계약 정보를 저장했습니다.')
                return redirect('planning-contract-detail', contract_id=saved.pk)
    metadata = {str(p.site_id): {**{key: getattr(p, key) for key in ['show_in_list', 'include_in_total', 'display_as', 'category', 'region']},
                               'partner_public': 'public' if p.partner_public else 'private', 'display_revision': p.updated_at.isoformat()}
                for p in presentations.values()}
    return render(request, 'planning/contract_form.html', {'form': form, 'products': products, 'sites': sites, 'site_metadata': metadata,
                                                          'customer': customer, 'contract': contract, 'has_products': Product.objects.exists()})


@planning_only
def contract_detail(request, contract_id):
    contract = get_object_or_404(Contract.objects.select_related('customer__organization', 'contracting_party', 'superseded_by__customer__organization'), pk=contract_id)
    lines = list(contract.product_lines.select_related('product').all())
    links = list(contract.site_links.select_related('site').prefetch_related('product_selections__contract_product__product').all())
    return render(request, 'planning/contract_detail.html', {'contract': contract, 'lines': lines, 'links': links, 'total_quantity': sum(line.quantity for line in lines)})


@planning_only
@require_http_methods(['GET', 'POST'])
def contract_end(request, contract_id):
    contract = get_object_or_404(Contract.objects.select_related('customer__organization'), pk=contract_id)
    error = ''
    if request.method == 'POST':
        try:
            end_contract(request.user, contract.pk, request.POST.get('revision'))
        except ValidationError as failure:
            error = ' '.join(failure.messages)
        except DatabaseError:
            error = '계약 상태를 저장하지 못했습니다. 최신 내용을 확인하고 다시 시도해 주세요.'
        else:
            messages.success(request, '계약을 종료했습니다. 과거 기록은 유지됩니다.')
            return redirect('planning-contract-detail', contract_id=contract.pk)
    return render(request, 'planning/contract_end.html', {'contract': contract, 'error': error})


@planning_only
@require_http_methods(['GET', 'POST'])
def site_edit(request, site_id):
    site = get_object_or_404(InstallationSite, pk=site_id)
    p = SitePresentation.objects.filter(site=site).first()
    initial = presentation_initial(p, site.official_name) if p else {'official_name': site.official_name, 'display_as': DisplayKind.SITE,
                                                                  'show_in_list': False, 'include_in_total': False}
    form = PresentationForm(request.POST if request.method == 'POST' else None, request.FILES or None,
                            initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            save_presentation(request.user, form.cleaned_data, site_id=site_id)
        except (ValidationError, DatabaseError) as error:
            attach_errors(form, error)
        else:
            messages.success(request, '설치 장소 표시 설정을 저장했습니다.')
            return redirect('planning-site-edit', site_id=site_id)
    return render(request, 'planning/presentation_form.html', {'form': form, 'presentation': p, 'site': site, 'is_site': True})


@planning_only
def logo(request, kind, object_id):
    model = Customer if kind == 'customer' else SitePresentation if kind == 'site' else None
    if model is None:
        raise Http404
    obj = get_object_or_404(model, pk=object_id)
    if not obj.logo:
        raise Http404
    try:
        response = FileResponse(BytesIO(logo_bytes(obj)), content_type='image/png' if obj.logo.name.lower().endswith('.png') else 'image/jpeg')
    except (FileNotFoundError, OSError):
        raise Http404 from None
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@planning_only
@require_http_methods(['GET', 'POST'])
def product_add(request, product_id=None):
    product = get_object_or_404(Product, pk=product_id) if product_id else None
    initial = {**{key: getattr(product, key) for key in ['code', 'name', 'marker', 'color']}, 'revision': product.updated_at.isoformat()} if product else None
    form = ProductCatalogForm(request.POST if request.method == 'POST' else None, initial=initial, instance=product)
    if request.method == 'POST' and form.is_valid():
        try:
            save_product(request.user, form.cleaned_data, product_id=product_id)
        except (ValidationError, DatabaseError) as error:
            attach_errors(form, error)
        else:
            messages.success(request, '제품 정보를 저장했습니다.')
            return redirect('planning-product-add')
    return render(request, 'planning/product_form.html', {'form': form, 'catalog': ordered_products(Product.objects.all()), 'editing_product': product})


@planning_only
@require_http_methods(['GET', 'POST'])
def duplicate_merge_search(request, customer_id):
    primary = get_object_or_404(Customer.objects.select_related('organization'), pk=customer_id)
    if primary.merged_into_id:
        messages.error(request, '이미 통합된 고객사입니다. 유지된 고객사에서 중복 통합을 시작해 주세요.')
        return redirect('planning-customer-detail', customer_id=primary.merged_into_id)
    query = request.GET.get('q', '').strip()
    candidates = duplicate_candidates(primary, query)
    form = DuplicateSearchForm(request.POST if request.method == 'POST' else None, candidates=candidates, initial={'q': query})
    if request.method == 'POST' and form.is_valid():
        ids = [str(customer.pk) for customer in form.cleaned_data['duplicates']]
        return redirect(reverse('planning-duplicate-review', args=[primary.pk]) + '?' + urlencode([('d', value) for value in ids]))
    return render(request, 'planning/duplicate_merge_search.html', {'primary': primary, 'form': form, 'query': query})


def _duplicate_merge_groups(primary, duplicate_ids, post):
    duplicates = list(Customer.objects.select_related('organization').filter(pk__in=duplicate_ids, merged_into__isnull=True)
                      .exclude(pk=primary.pk).order_by('organization__official_name'))
    # Already-ended contracts move over as history automatically; only active ones can double
    # count a quantity, so only those need an explicit include/exclude decision here.
    contracts = list(Contract.objects.filter(customer__in=duplicates, is_active=True)
                     .select_related('customer__organization', 'contracting_party').prefetch_related('product_lines__product')
                     .order_by('customer_id', '-created_at'))
    initial = [{'contract_id': contract.pk, 'action': 'include'} for contract in contracts]
    formset = DuplicateContractFormSet(post, initial=initial, form_kwargs={'primary_contracts': primary.contracts.all()})
    rows_by_duplicate = {}
    for contract, form in zip(contracts, formset.forms):
        rows_by_duplicate.setdefault(contract.customer_id, []).append((contract, form))
    groups = [(duplicate, rows_by_duplicate.get(duplicate.pk, [])) for duplicate in duplicates]
    return duplicates, groups, formset


@planning_only
@require_http_methods(['GET', 'POST'])
def duplicate_merge_review(request, customer_id):
    primary = get_object_or_404(Customer.objects.select_related('organization'), pk=customer_id)
    if primary.merged_into_id:
        messages.error(request, '이미 통합된 고객사입니다. 유지된 고객사에서 중복 통합을 시작해 주세요.')
        return redirect('planning-customer-detail', customer_id=primary.merged_into_id)
    duplicate_ids = request.POST.getlist('duplicate_ids') if request.method == 'POST' else request.GET.getlist('d')
    duplicates, groups, contract_formset = _duplicate_merge_groups(primary, duplicate_ids, request.POST if request.method == 'POST' else None)
    if not duplicates:
        messages.error(request, '통합할 중복 고객사를 먼저 선택해 주세요.')
        return redirect('planning-duplicate-search', customer_id=primary.pk)
    ended_count = Contract.objects.filter(customer__in=duplicates, is_active=False).count()
    presentation_form = PresentationForm(request.POST if request.method == 'POST' else None, request.FILES or None,
                                         initial=presentation_initial(primary, str(primary)))
    if request.method == 'POST':
        valid = [presentation_form.is_valid(), contract_formset.is_valid()]
        if all(valid):
            decisions = {str(form.cleaned_data['contract_id'].pk): form.decision() for form in contract_formset.forms}
            try:
                merged = merge_duplicate_customers(request.user, primary.pk, [d.pk for d in duplicates], presentation_form.cleaned_data, decisions)
            except (ValidationError, DatabaseError) as error:
                attach_errors(presentation_form, error)
            else:
                messages.success(request, f'{len(duplicates)}곳의 중복 고객사를 "{merged}"(으)로 통합했습니다.')
                return redirect('planning-customer-detail', customer_id=merged.pk)
    return render(request, 'planning/duplicate_merge_review.html', {
        'primary': primary, 'duplicates': duplicates, 'groups': groups, 'ended_count': ended_count,
        'presentation_form': presentation_form, 'contract_formset': contract_formset,
    })


@planning_only
@require_http_methods(['POST'])
def product_delete(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    try:
        delete_product(request.user, product.pk)
    except ValidationError as failure:
        messages.error(request, ' '.join(failure.messages))
    except DatabaseError:
        messages.error(request, '제품을 삭제하지 못했습니다. 잠시 후 다시 시도해 주세요.')
    else:
        messages.success(request, f'"{product.name}" 제품을 삭제했습니다.')
    return redirect('planning-product-add')
