from functools import wraps
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.http import FileResponse, Http404, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods
from .models import Category, Region, DisplayKind, Customer, Contract, SitePresentation, Product
from .portal_forms import DeliveryAuthenticationForm, PerformanceFilterForm, AccountCreateForm, AccountEditForm, AccountPasswordForm
from .planning_views import planning_only, attach_errors
from .services.access import audience_for_user, require_employee, require_manager
from .services.accounts import account_role, account_revision, create_account, update_account, reset_account_password
from .services.audience_performance import current_performance_payload
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
    audience = audience_for_user(request.user)
    form = PerformanceFilterForm(request.GET)
    valid = form.is_valid()
    data = form.cleaned_data if valid else {'products': [], 'category': [], 'q': ''}
    product_ids = [str(p.pk) for p in data['products']]
    categories = list(data['category'])
    search = data['q']
    if valid:
        payload = current_performance_payload(request.user, selected_product_ids=product_ids, categories=categories)
    else:
        payload = {'items': [], 'counts': {'total': 0, 'public': 0, 'private': 0, 'by_category': {}, 'private_by_category': {}}}
    category_rank = {code: index for index, (code, _) in enumerate(Category.choices)}
    selected_ids = set(product_ids)
    items = sorted(payload['items'], key=lambda row: (category_rank[row['category']], row['name'].casefold(), row['kind'], row['id']))
    for item in items:
        item['category_label'] = Category(item['category']).label
        item['region_label'] = Region(item['region']).label if item['region'] else ''
        item['display_label'] = DisplayKind(item['display_as']).label
        for product in item['products']:
            product['emphasized'] = bool(selected_ids) and product['id'] in selected_ids
            product['subdued'] = bool(selected_ids) and product['id'] not in selected_ids
        item['products'] = sorted(item['products'], key=lambda p: (p['subdued'], p['name'], p['id']))
    # The name search only narrows what is listed; counts, sections and printing ignore it.
    if search:
        needle = search.casefold()
        items = [item for item in items if needle in item['name'].casefold()]
    print_query = filter_query(product_ids, categories)
    page_query = filter_query(product_ids, categories, search)
    groups = [{'code': value, 'label': label, 'count': payload['counts']['by_category'].get(value, 0),
               'private_count': payload['counts']['private_by_category'].get(value, 0)} for value, label in Category.choices]
    page = Paginator(items, 24).get_page(request.GET.get('page'))
    previous_category = items[page.start_index() - 2]['category'] if page.has_previous() else None
    visible_categories = {item['category'] for item in items}
    list_groups = []
    for group in groups:
        rows = [item for item in page if item['category'] == group['code']]
        # A counted-only/private-only category is still represented numerically,
        # once on the first page. Never fabricate cards for those customers.
        if rows or (page.number == 1 and group['count'] and group['code'] not in visible_categories and not search):
            list_groups.append({**group, 'items': rows, 'continued': bool(rows) and previous_category == group['code']})
    # Every tab and chip is a link that toggles one value; products and categories are both multi-select.
    def toggled_url(products, chosen_categories):
        return filter_url(request.path, filter_query(products, chosen_categories, search))

    category_tabs = [{'code': '', 'label': '전체', 'full_label': '전체 분류', 'active': not categories,
                      'url': toggled_url(product_ids, [])}]
    for code, label in Category.choices:
        chosen = [value for value, _ in Category.choices if (value in categories) != (value == code)]
        category_tabs.append({'code': code, 'label': SHORT_CATEGORY_LABELS[code], 'full_label': label,
                              'active': code in categories, 'url': toggled_url(product_ids, chosen)})
    product_chips = []
    for product in form.product_catalog():
        active = product['id'] in selected_ids
        chosen = [value for value in product_ids if value != product['id']] if active else product_ids + [product['id']]
        product_chips.append({**product, 'active': active, 'url': toggled_url(chosen, categories)})
    return render(request, 'portal/performance.html', {
        'form': form, 'page': page, 'counts': payload['counts'], 'groups': groups, 'list_groups': list_groups,
        'filter_query': page_query.urlencode(), 'print_query': print_query.urlencode(),
        'has_filters': bool(product_ids or categories), 'search_query': search,
        'clear_search_url': filter_url(request.path, print_query),
        'category_tabs': category_tabs, 'selected_categories': categories,
        'selected_category_labels': [label for code, label in Category.choices if code in categories],
        'show_category_strip': not categories, 'product_chips': product_chips,
        'active_products': [chip for chip in product_chips if chip['active']],
        'is_partner': audience == 'partner', 'filters_valid': valid}, status=200 if valid else 400)


@employee_only
@require_GET
def customer_detail(request, customer_id):
    customer = get_object_or_404(Customer.objects.select_related('organization'), pk=customer_id)
    quantities = customer_current_quantities(customer.pk)
    products = {str(p.pk): p for p in Product.objects.filter(pk__in=quantities)}
    totals = sorted([(products[key], value) for key, value in quantities.items()], key=lambda row: row[0].name)
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
@never_cache
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
    obj = get_object_or_404(rows.only('id', 'logo'), pk=object_id)
    if not obj.logo:
        raise Http404
    try:
        stream = obj.logo.open('rb')
    except (OSError, ValueError):
        raise Http404 from None
    content_type = 'image/png' if obj.logo.name.lower().endswith('.png') else 'image/jpeg'
    response = FileResponse(stream, content_type=content_type, filename='symbol.png' if content_type == 'image/png' else 'symbol.jpg')
    response['X-Content-Type-Options'] = 'nosniff'
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
    from .services.region_map import basis_date, region_map_payload
    return render(request, 'portal/region_map.html', {
        'payload': region_map_payload(),
        'basis_date': basis_date(),
    })
