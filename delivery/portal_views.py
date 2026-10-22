from functools import wraps
from io import BytesIO
from time import perf_counter
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.http import FileResponse, Http404, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.utils.cache import add_never_cache_headers, patch_cache_control
from django.views.decorators.http import require_GET, require_http_methods
from .services.list_order import item_order_key
from .services.logo_cache import logo_bytes
from .domain.products import product_sort_key
from .templatetags.delivery_display import badge_color
from .models import Category, Region, DisplayKind, Customer, Contract, SitePresentation, Product
from .portal_forms import DeliveryAuthenticationForm, PerformanceFilterForm, AccountCreateForm, AccountEditForm, AccountPasswordForm
from .planning_views import planning_only, attach_errors
from .services.access import audience_for_user, require_employee, require_manager
from .services.accounts import account_role, account_revision, create_account, update_account, reset_account_password
from .services.audience_performance import current_performance_payload
from .services.sections import section_of, section_rank, sections as list_sections
from .services.current_performance import customer_current_quantities, current_customers_with_any_products, current_site_presentations_with_any_products


class DeliveryLoginView(LoginView):
    authentication_form = DeliveryAuthenticationForm
    template_name = 'planning/login.html'
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        try:
            require_manager(self.request.user)
        except PermissionDenied:
            return '/performance/'
        return '/planning/'


def employee_only(view):
    @wraps(view)
    @login_required
    @never_cache
    def wrapped(request, *args, **kwargs):
        require_employee(request.user)
        return view(request, *args, **kwargs)
    return wrapped


SHORT_CATEGORY_LABELS = {Category.CENTRAL: '중앙정부', Category.PUBLIC: '공공', Category.LOCAL: '지자체', Category.COUNCIL: '지자체 의회',
                         Category.FINANCE: '금융', Category.EDUCATION: '교육', Category.OVERSEAS: '해외', Category.PRIVATE: '민간'}


def filter_query(products=(), categories=(), search=''):
    """Canonical, server-validated list state. Only products and categories ever reach printing."""
    query = QueryDict('', mutable=True)
    if products:
        query.setlist('products', [str(value) for value in products])
    if categories:
        query.setlist('category', list(categories))
    if search:
        query['q'] = search
    return query


def filter_url(path, query):
    encoded = query.urlencode()
    return f'{path}?{encoded}' if encoded else path


@login_required
@never_cache
@require_GET
def performance(request):
    started = perf_counter()
    audience = audience_for_user(request.user)
    form = PerformanceFilterForm(request.GET)
    valid = form.is_valid()
    data = form.cleaned_data if valid else {'products': [], 'category': [], 'q': ''}
    product_ids = [str(p.pk) for p in data['products']]
    categories = list(data['category'])
    search = data['q']
    # 제품·분류를 하나도 안 고른 화면은 브라우저가 '전체 목록'으로 들고 있다가 칩을 누르면 그 자리에서 고른다(2026-10-22 형우: 속도)
    base_view = valid and not product_ids and not categories
    if valid:
        payload = current_performance_payload(request.user, selected_product_ids=product_ids, categories=categories, with_index=base_view)
    else:
        payload = {'items': [], 'counts': {'total': 0, 'public': 0, 'private': 0, 'by_category': {}, 'private_by_category': {}}}
    selected_ids = set(product_ids)
    # 분류 → (지자체·의회는) 권역 → 이름 순(C2). 중앙정부·민간·지자체는 정한 순서(services/list_order, 2026-10-22 형우).
    order = item_order_key(payload['items'])
    items = sorted(payload['items'], key=lambda row: (*section_rank(row['category'], row['region']), *order(row), row['kind'], row['id']))
    # 카드 주소·로고 주소·마킹 색은 여기서 한 번에 만든다 — 504장을 그릴 때 템플릿이 매번 계산하지 않게(2026-10-22, 속도)
    zero = '00000000-0000-0000-0000-000000000000'
    detail_base = {'customer': reverse('employee-customer', args=[zero]), 'site': reverse('employee-site', args=[zero])}
    logo_base = {kind: reverse('performance-logo', args=[kind, zero]) for kind in detail_base}
    catalog = form.product_catalog()
    product_bit = {product['id']: 1 << index for index, product in enumerate(catalog)} if len(catalog) <= 30 else {}
    for item in items:
        item['pm'] = sum(product_bit.get(product['id'], 0) for product in item['products'])
        item['detail_url'] = detail_base[item['kind']].replace(zero, item['id'])
        item['logo_url'] = logo_base[item['kind']].replace(zero, item['id']) if item['has_logo'] else ''
        item['initial'] = item['name'][:1]
        item['category_label'] = Category(item['category']).label
        item['region_label'] = Region(item['region']).label if item['region'] else ''
        item['display_label'] = DisplayKind(item['display_as']).label
        for product in item['products']:
            product['emphasized'] = bool(selected_ids) and product['id'] in selected_ids
            product['subdued'] = bool(selected_ids) and product['id'] not in selected_ids
            product['badge'] = badge_color(product['color'])
            product['bit'] = product_bit.get(product['id'], 0)
        item['products'] = sorted(item['products'], key=lambda p: (p['subdued'], *product_sort_key(p['marker'], p['name'], p['id'])))
    # The name search only narrows what is listed; counts, sections and printing ignore it.
    if search:
        needle = search.casefold()
        items = [item for item in items if needle in item['name'].casefold()]
    print_query = filter_query(product_ids, categories)
    page_query = filter_query(product_ids, categories, search)
    # 분류 칸(2026-10-22 형우: 탭 대신 요약 칸을 버튼으로). 칸 숫자는 분류 선택과 상관없이 각자 숫자를 보여준다.
    # 제품 필터는 반영한다. 큰 숫자(counts.total)는 고른 분류의 합 그대로.
    chip_counts = (current_performance_payload(request.user, selected_product_ids=product_ids, categories=[])['counts']
                   if valid and categories else payload['counts'])
    groups = [{'code': value, 'label': label, 'count': chip_counts['by_category'].get(value, 0),
               'private_count': chip_counts['private_by_category'].get(value, 0)} for value, label in Category.choices]
    # 2026-10-22 형우: 페이지를 없앤다(고객사 명부라 한 화면에). 전체 보기에서는 섹션을 두 줄로 접고(화면에서),
    # 분류를 골랐거나 검색 중이면 다 펼친다. 'page'는 기존 템플릿·검사와 맞추려고 한 장짜리로 둔다.
    page = Paginator(items, max(len(items), 1)).get_page(1)
    # 섹션은 분류 단위, 지자체·의회만 권역 단위(C2). 요약 칸(groups)은 분류 단위 그대로.
    item_section = lambda item: section_of(item['category'], item['region'])
    visible_sections = {item_section(item) for item in items}
    list_groups = []
    for group in list_sections(payload['counts']):
        section = (group['code'], group['region'])
        rows = [item for item in items if item_section(item) == section]
        # A counted-only/private-only section is still represented numerically. Never fabricate cards for those customers.
        if rows or (group['count'] and section not in visible_sections and not search):
            list_groups.append({**group, 'items': rows, 'continued': False})
    # Every tab and chip is a link that toggles one value; products and categories are both multi-select.
    def toggled_url(products, chosen_categories):
        return filter_url(request.path, filter_query(products, chosen_categories, search))

    category_tabs = [{'code': '', 'label': '전체', 'full_label': '전체 분류', 'active': not categories,
                      'url': toggled_url(product_ids, [])}]
    for code, label in Category.choices:
        chosen = [value for value, _ in Category.choices if (value in categories) != (value == code)]
        category_tabs.append({'code': code, 'label': SHORT_CATEGORY_LABELS[code], 'full_label': label,
                              'active': code in categories, 'url': toggled_url(product_ids, chosen)})
    tab_by_code = {tab['code']: tab for tab in category_tabs}
    for group in groups:
        group.update(active=tab_by_code[group['code']]['active'], url=tab_by_code[group['code']]['url'])
    product_chips = []
    for product in catalog:
        active = product['id'] in selected_ids
        chosen = [value for value in product_ids if value != product['id']] if active else product_ids + [product['id']]
        product_chips.append({**product, 'active': active, 'url': toggled_url(chosen, categories)})
    count_index = None
    if base_view and product_bit:
        keys = []
        rows = []
        for category, region, public, ids in payload.get('index', []):
            section = section_of(category, region)
            key = f'{section[0]}-{section[1]}' if section[1] else section[0]
            if key not in keys:
                keys.append(key)
            rows.append([keys.index(key), category, 1 if public else 0, sum(product_bit.get(value, 0) for value in ids)])
        count_index = {'products': [product['id'] for product in catalog], 'sections': keys, 'rows': rows}
    if hasattr(request, 'timing'):
        request.timing['data'] = (perf_counter() - started) * 1000   # 자료 준비 시간(나머지는 화면 그리기)
    return render(request, 'portal/performance.html', {
        'form': form, 'page': page, 'counts': payload['counts'], 'groups': groups, 'list_groups': list_groups,
        'collapse_sections': not categories and not search,
        'filter_query': page_query.urlencode(), 'print_query': print_query.urlencode(),
        'has_filters': bool(product_ids or categories), 'search_query': search,
        'clear_search_url': filter_url(request.path, print_query),
        'category_tabs': category_tabs, 'selected_categories': categories,
        'selected_category_labels': [label for code, label in Category.choices if code in categories],
        'show_category_strip': valid, 'product_chips': product_chips,
        'active_products': [chip for chip in product_chips if chip['active']],
        'is_partner': audience == 'partner', 'filters_valid': valid, 'count_index': count_index}, status=200 if valid else 400)


@employee_only
@require_GET
def customer_detail(request, customer_id):
    customer = get_object_or_404(Customer.objects.select_related('organization'), pk=customer_id)
    quantities = customer_current_quantities(customer.pk)
    products = {str(p.pk): p for p in Product.objects.filter(pk__in=quantities)}
    totals = sorted([(products[key], value) for key, value in quantities.items()], key=lambda row: product_sort_key(row[0].marker, row[0].name, row[0].pk))
    contracts = customer.contracts.select_related('contracting_party').prefetch_related('product_lines__product').defer(
        'source_email_subject', 'source_email_sender', 'source_email_received_on').order_by('-created_at')
    return render(request, 'portal/customer_detail.html', {'customer': customer, 'totals': totals,
                    'total_quantity': sum(quantities.values()), 'contracts': contracts})


@employee_only
@require_GET
def contract_detail(request, contract_id):
    contract = get_object_or_404(Contract.objects.select_related('customer__organization', 'contracting_party').defer(
        'source_email_subject', 'source_email_sender', 'source_email_received_on'), pk=contract_id)
    lines = list(contract.product_lines.select_related('product'))
    links = contract.site_links.select_related('site').prefetch_related('product_selections__contract_product__product')
    return render(request, 'portal/contract_detail.html', {'contract': contract, 'lines': lines, 'links': links,
                    'total_quantity': sum(line.quantity for line in lines)})


@employee_only
@require_GET
def site_detail(request, presentation_id):
    presentation = get_object_or_404(SitePresentation.objects.select_related('site'), pk=presentation_id)
    contracts = Contract.objects.filter(site_links__site=presentation.site).select_related('customer__organization', 'contracting_party').defer(
        'source_email_subject', 'source_email_sender', 'source_email_received_on').distinct().order_by('-created_at')
    return render(request, 'portal/site_detail.html', {'presentation': presentation, 'contracts': contracts})


@login_required
@require_GET
def logo(request, kind, object_id):
    audience = audience_for_user(request.user)
    if kind == 'customer':
        rows = Customer.objects.all() if audience == 'employee' else current_customers_with_any_products(())
    elif kind == 'site':
        rows = SitePresentation.objects.all() if audience == 'employee' else current_site_presentations_with_any_products(())
    else:
        raise Http404
    if audience == 'partner':
        rows = rows.filter(show_in_list=True, partner_public=True)
    obj = get_object_or_404(rows.only('id', 'logo', 'updated_at'), pk=object_id)
    if not obj.logo:
        raise Http404
    try:
        stream = BytesIO(logo_bytes(obj))   # 권한 확인은 매번, 파일 내용은 서버 메모리에서(2026-10-22)
    except (OSError, ValueError):
        raise Http404 from None
    content_type = 'image/png' if obj.logo.name.lower().endswith('.png') else 'image/jpeg'
    response = FileResponse(stream, content_type=content_type, filename='symbol.png' if content_type == 'image/png' else 'symbol.jpg')
    response['X-Content-Type-Options'] = 'nosniff'
    if audience == 'partner':
        add_never_cache_headers(response)   # 파트너사는 공개 정책이 바뀌면 바로 따라야 해서 저장하지 않는다(기존 그대로)
    else:
        patch_cache_control(response, private=True, max_age=3600)   # 직원은 이 기기에 1시간 보관(2026-10-22, 속도)
    return response


@planning_only
@require_GET
def account_list(request):
    users = get_user_model().objects.select_related('delivery_access').prefetch_related('user_permissions', 'groups').order_by('username')
    query = request.GET.get('q', '').strip()
    if query:
        from django.db.models import Q
        users = users.filter(Q(username__icontains=query) | Q(first_name__icontains=query))
    page = Paginator(users, 24).get_page(request.GET.get('page'))
    for user in page:
        user.role_label = {'employee': '직원', 'partner': '파트너사', 'manager': '기획팀 관리자'}.get(account_role(user), '권한 미설정')
        user.locally_managed = not (user.is_staff or user.is_superuser or user.groups.exists())
    return render(request, 'portal/accounts.html', {'page': page, 'query': query})


@planning_only
@require_http_methods(['GET', 'POST'])
def account_new(request):
    form = AccountCreateForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            user = create_account(request.user, form.cleaned_data)
        except (ValidationError, DatabaseError) as error:
            attach_errors(form, error)
        else:
            messages.success(request, '계정을 만들었습니다. 정한 아이디와 비밀번호를 이용자에게 직접 안내해 주세요.')
            return redirect('account-edit', user_id=user.pk)
    return render(request, 'portal/account_form.html', {'form': form, 'creating': True})


@planning_only
@require_http_methods(['GET', 'POST'])
def account_edit(request, user_id):
    user = get_object_or_404(get_user_model(), pk=user_id)
    form = AccountEditForm(request.POST if request.method == 'POST' else None,
        initial={'first_name': user.first_name, 'role': account_role(user), 'is_active': user.is_active, 'revision': account_revision(user)})
    if request.method == 'POST' and form.is_valid():
        try:
            update_account(request.user, user.pk, form.cleaned_data)
        except (ValidationError, DatabaseError) as error:
            attach_errors(form, error)
        else:
            messages.success(request, '계정 설정을 저장했습니다.')
            return redirect('accounts')
    return render(request, 'portal/account_form.html', {'form': form, 'editing_user': user})


@planning_only
@require_http_methods(['GET', 'POST'])
def account_password(request, user_id):
    user = get_object_or_404(get_user_model(), pk=user_id)
    form = AccountPasswordForm(user, request.POST if request.method == 'POST' else None, initial={'revision': account_revision(user)})
    if request.method == 'POST' and form.is_valid():
        try:
            reset_account_password(request.user, user.pk, form.cleaned_data)
        except (ValidationError, DatabaseError) as error:
            attach_errors(form, error)
        else:
            if user.pk == request.user.pk:
                logout(request)
                messages.success(request, '비밀번호를 바꿨습니다. 새 비밀번호로 다시 로그인해 주세요.')
                return redirect('login')
            messages.success(request, '비밀번호를 재설정했습니다. 이 계정은 새 비밀번호로 다시 로그인해야 합니다.')
            return redirect('accounts')
    return render(request, 'portal/account_password.html', {'form': form, 'editing_user': user})


@employee_only
@require_GET
def region_map(request):
    """8단계 지역 현황(지자체·의회 지도). 직원 전용."""
    import logging
    from .services.region_map import basis_date, region_map_payload
    manager = True
    try:
        require_manager(request.user)
    except PermissionDenied:
        manager = False
    try:
        payload, basis = region_map_payload(show_unassigned=manager), basis_date()
    except DatabaseError:
        logging.getLogger(__name__).exception('region map payload failed')
        return render(request, 'portal/region_map.html', {'payload_error': True}, status=503)
    return render(request, 'portal/region_map.html', {'payload': payload, 'basis_date': basis})
