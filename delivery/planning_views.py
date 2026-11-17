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
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from .forms import site_display_of, PresentationForm, ContractForm, ProductFormSet, SiteFormSet, ProductCatalogForm, DuplicateSearchForm, DuplicateContractFormSet
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


LOGO_WARNINGS = {
    'low_res': '해상도가 낮습니다. 긴 변 300px 이상인 파일을 권장합니다.',
    'too_wide': '가로로 너무 깁니다. 기관 이름 글자가 들어 있지 않은지 확인해 주세요.',
    'too_tall': '세로로 너무 깁니다. 기관 이름 글자가 들어 있지 않은지 확인해 주세요.',
    'colored_background': '배경색이 있어 그대로 둡니다. 배경이 심볼의 일부인지 확인해 주세요.',
    'unreadable': '이 파일은 읽을 수 없습니다. PNG나 JPG로 다시 저장해 주세요.',
    'empty': '그림이 비어 있습니다.',
}


def logo_preview_context(presentation, kind):
    """심볼 미리보기(2026-11-17 형우): 실제 카드 크기로, 이미 등록된 심볼 3개 옆에 놓고 비교한다."""
    from .services.logo_renditions import logo_class, logo_signature, visible_logo_targets
    samples = [logo_class(obj.pk) for _, obj in visible_logo_targets('employee')[:3]]
    return {'logo_css_url': reverse('performance-logo-css') + '?v=' + logo_signature('employee'), 'logo_samples': samples,
            'logo_kind': kind, 'logo_id': str(presentation.pk) if presentation is not None and presentation.logo else '',
            'logo_as_is': bool(presentation is not None and presentation.logo and presentation.logo_fit == 'as_is')}


@planning_only
@require_http_methods(['POST'])
def logo_preview(request):
    """올리려는 파일(또는 저장된 심볼)을 화면 카드용으로 정리한 모습과 경고. 저장은 하지 않는다."""
    import base64
    from .services.logo_renditions import make
    upload = request.FILES.get('logo')
    size = request.POST.get('logo_size') if request.POST.get('logo_size') in {'small', 'normal', 'large'} else 'normal'
    background = request.POST.get('logo_background') if request.POST.get('logo_background') in {'remove', 'keep'} else 'remove'
    if upload is not None:
        if upload.size > 2 * 1024 * 1024:
            return JsonResponse({'image': '', 'warnings': ['파일이 2MB보다 큽니다.']}, status=400)
        data, fit = upload.read(), 'auto'
    else:
        model = {'customer': Customer, 'site': SitePresentation}.get(request.POST.get('kind'))
        if model is None:
            raise Http404
        obj = get_object_or_404(model, pk=request.POST.get('id'))
        if not obj.logo:
            raise Http404
        try:
            data = logo_bytes(obj)
        except (OSError, ValueError):
            raise Http404 from None
        fit = 'auto' if obj.logo_fit == 'auto' or request.POST.get('logo_auto') else 'as_is'
    web, _printed, info = make(data, fit, size, background, need_print=False)
    response = JsonResponse({'image': 'data:image/webp;base64,' + base64.b64encode(web).decode('ascii') if web else '',
                             'fit': fit, 'warnings': [LOGO_WARNINGS.get(code, code) for code in info.get('warnings', [])]})
    response['Cache-Control'] = 'private, no-store'
    return response


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
    # 월별 보기(2026-11-17 형우): 등록월·계약월 두 기준, 신규 고객사 / 계약 추가
    from .services.customer_months import month_index, note_for, _month
    basis = request.GET.get('basis') if request.GET.get('basis') in {'registered', 'contract'} else 'registered'
    month = request.GET.get('month', '')
    kind = request.GET.get('kind') if request.GET.get('kind') in {'new', 'added'} else ''
    marks, months = month_index(basis)
    month_counts = {key: (new, added) for key, _label, new, added in months}
    if month not in month_counts:
        month, kind = '', ''
    if month:
        ids = [cid for cid, customer_marks in marks.items() if month in customer_marks and (not kind or customer_marks[month][0] == kind)]
        day_of = lambda customer: marks[customer.pk][month][1] or customer.created_at.date()
        rows = sorted(rows.filter(pk__in=ids), key=lambda customer: (-day_of(customer).toordinal(), customer.organization.official_name))
    page = Paginator(rows, 24).get_page(request.GET.get('page'))
    # 심볼 없는 고객사는 계약 당사자의 심볼을 빌려 쓴다(납품현황과 같은 규칙, 2026-11-17 형우)
    from .services.logo_renditions import logo_fallbacks
    borrowed = logo_fallbacks([{'kind': 'customer', 'id': str(c.pk), 'has_logo': bool(c.logo)} for c in page], 'employee')
    for customer in page:
        badges = {line.product_id: line.product for contract in customer.current_contracts for line in contract.product_lines.all()}
        # 제품 순서는 어디서나 I, S, B, D, P, H, C(2026-10-22 형우). 여기만 이름순이었다.
        customer.product_badges = sorted(badges.values(), key=lambda product: product_sort_key(product.marker, product.name, product.pk))
        customer.needs_location = customer.category in LOCATION_CATEGORIES and not customer.location_code
        customer.borrowed_logo = borrowed.get(('customer', str(customer.pk)), '')
        customer.month_note = note_for(basis, *marks[customer.pk][month]) if month else ''
    this_month = _month(timezone.localdate())
    return render(request, 'planning/customer_list.html', {
        'page': page, 'query': query, 'selected_category': category, 'categories': Category.choices,
        'basis': basis, 'month': month, 'kind': kind, 'months': months,
        'month_new': month_counts.get(month, (0, 0))[0], 'month_added': month_counts.get(month, (0, 0))[1],
        'this_month': this_month, 'this_month_counts': month_counts.get(this_month, (0, 0))})


def presentation_initial(obj, name):
    return {**{field: getattr(obj, field) for field in ['category', 'region', 'include_in_total', 'show_in_list', 'display_as', 'memo', 'logo_size', 'logo_background']},
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
                                                               'location_data': location_data(), **logo_preview_context(customer, 'customer')})


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
                data.update({key: getattr(p, key) for key in ['display_as', 'category', 'region']}, site_display=site_display_of(p))
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
    metadata = {str(p.site_id): {**{key: getattr(p, key) for key in ['display_as', 'category', 'region']}, 'site_display': site_display_of(p),
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
def contract_delete(request, contract_id):
    """잘못 넣은 계약 삭제(2026-11-17 형우). GET은 확인 화면, POST가 삭제. 실제로 끝난 계약은 '계약 종료'."""
    from .services.contract_delete import contract_deletion_plan, delete_contract
    contract = get_object_or_404(Contract.objects.select_related('customer__organization', 'contracting_party'), pk=contract_id)
    error = ''
    if request.method == 'POST':
        try:
            customer = delete_contract(request.user, contract.pk, request.POST.get('revision'))
        except ValidationError as failure:
            error = ' '.join(failure.messages)
        except DatabaseError:
            error = '계약을 삭제하지 못했습니다. 잠시 후 다시 시도해 주세요.'
        else:
            messages.success(request, '계약을 삭제했습니다.')
            return redirect('planning-customer-detail', customer_id=customer.pk)
    return render(request, 'planning/contract_delete.html', {'contract': contract, 'plan': contract_deletion_plan(contract), 'error': error})


@planning_only
@require_http_methods(['GET', 'POST'])
def site_edit(request, site_id):
    site = get_object_or_404(InstallationSite, pk=site_id)
    p = SitePresentation.objects.filter(site=site).first()
    initial = ({**presentation_initial(p, site.official_name), 'site_display': site_display_of(p)} if p else
               {'official_name': site.official_name, 'display_as': DisplayKind.SITE, 'site_display': 'none'})
    form = PresentationForm(request.POST if request.method == 'POST' else None, request.FILES or None,
                            initial=initial, for_site=True)
    if request.method == 'POST' and form.is_valid():
        try:
            save_presentation(request.user, form.cleaned_data, site_id=site_id)
        except (ValidationError, DatabaseError) as error:
            attach_errors(form, error)
        else:
            messages.success(request, '설치 장소 표시 설정을 저장했습니다.')
            return redirect('planning-site-edit', site_id=site_id)
    return render(request, 'planning/presentation_form.html', {'form': form, 'presentation': p, 'site': site, 'is_site': True,
                                                               **logo_preview_context(p, 'site')})


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
