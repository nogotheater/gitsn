"""Audience HTTP and account security tests on Django's isolated PostgreSQL DB."""
from tempfile import TemporaryDirectory
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from delivery.models import Customer, Organization, Contract, ContractProduct, ContractSite, InstallationSite, SitePresentation, SiteProductSelection, Product, UserAccessProfile
from delivery.services.accounts import create_account, account_revision, update_account
from .test_planning_forms import image_upload


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PortalHttpScenarios(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.manager = cls.user('manager', 'employee')
        cls.manager.user_permissions.add(Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery'))
        cls.employee = cls.user('employee', 'employee')
        cls.partner = cls.user('partner', 'partner')
        cls.c = Product.objects.create(code='portal-c', name='가상 C', marker='C')
        cls.i = Product.objects.create(code='portal-i', name='가상 I', marker='I')
        cls.public = cls.customer('공개 가상 기관', True, 'public')
        cls.secret = cls.customer('SECRET_TARGET_SENTINEL', False, 'private')
        cls.single = cls.customer('단일 제품 가상 기관', True, 'public')
        cls.local = cls.customer('가상 시청', True, 'local', 'capital')
        cls.public_c = cls.contract(cls.public, cls.c, 10)
        cls.contract(cls.public, cls.i, 5)
        cls.secret_c = cls.contract(cls.secret, cls.c, 33)
        cls.secret_i = cls.contract(cls.secret, cls.i, 7)
        cls.contract(cls.single, cls.c, 2)
        cls.contract(cls.local, cls.c, 4)
        cls.physical = InstallationSite.objects.create(official_name='공개 가상 장소')
        cls.site = SitePresentation.objects.create(site=cls.physical, category='public', partner_public=True, include_in_total=False)
        link = ContractSite.objects.create(contract=cls.public_c, site=cls.physical)
        SiteProductSelection.objects.create(contract_site=link, contract_product=cls.public_c.product_lines.get())

    @staticmethod
    def user(name, audience):
        user = get_user_model().objects.create_user(name, password='LocalPortalOnly!73')
        UserAccessProfile.objects.create(user=user, audience=audience)
        return user

    @staticmethod
    def customer(name, public, category, region=''):
        return Customer.objects.create(organization=Organization.objects.create(official_name=name), partner_public=public,
                                       category=category, region=region, memo='PRIVATE_MEMO_SENTINEL')

    @staticmethod
    def contract(customer, product, qty):
        contract = Contract.objects.create(customer=customer, contracting_party=customer.organization, is_active=True,
                  source_email_subject='SOURCE_SUBJECT_SENTINEL', source_email_sender='SOURCE_SENDER_SENTINEL')
        ContractProduct.objects.create(contract=contract, product=product, quantity=qty)
        return contract

    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=folder))

    def view(self, user, query=None):
        self.client.force_login(user)
        return self.client.get('/performance/', query or {})

    def account_data(self, **changes):
        return {**{'username': 'new-account', 'first_name': '', 'role': 'employee', 'password1': 'NewLocalExample!74', 'password2': 'NewLocalExample!74'}, **changes}

    def test_partner_response_has_only_public_rows_and_same_total_without_private_metadata(self):
        employee = self.view(self.employee)
        partner = self.view(self.partner, {'audience': 'employee'})
        self.assertEqual(employee.context['counts']['total'], 4)
        self.assertEqual(partner.context['counts']['total'], 4)
        self.assertEqual(partner.context['counts']['private'], 1)
        self.assertEqual(employee.context['page'].paginator.count, 5)
        self.assertEqual(partner.context['page'].paginator.count, 4)
        for secret in [str(self.secret.pk), str(self.secret_c.pk), str(self.secret_i.pk), 'SECRET_TARGET_SENTINEL', 'PRIVATE_MEMO_SENTINEL', 'SOURCE_SUBJECT_SENTINEL', '33대', '/performance/contracts/', '/planning/accounts/']:
            self.assertNotContains(partner, secret)
        self.assertNotContains(partner, '/performance/customers/')
        self.assertContains(employee, 'SECRET_TARGET_SENTINEL')
        self.assertContains(employee, '/performance/customers/')
        for text in ['10대', 'PRIVATE_MEMO_SENTINEL', 'SOURCE_SUBJECT_SENTINEL']:
            self.assertNotContains(employee, text)
        # 안내 줄 '계약 기준 실적 · 파트너사 열람'은 2026-10-21 형우 결정으로 삭제(납품현황 룩). 지금은 없어야 한다.
        self.assertNotContains(partner, '파트너사 열람')

    def test_any_selected_products_across_live_contracts_and_filters_share_counts(self):
        query = {'products': [str(self.c.pk), str(self.i.pk)]}
        for user in [self.employee, self.partner]:
            response = self.view(user, query)
            self.assertEqual(response.context['counts']['total'], 4)
            self.assertEqual(response.context['counts']['private'], 1)
            self.assertContains(response, '공개 가상 장소')
        response = self.view(self.partner, {**query, 'category': 'private'})
        self.assertEqual(response.context['counts']['total'], 1)
        self.assertEqual(response.context['page'].paginator.count, 0)
        self.assertContains(response, '비공개 1곳 포함')
        self.assertEqual(self.view(self.employee, {'category': 'local'}).context['counts']['total'], 1)
        self.assertEqual(self.view(self.partner, {'category': ['local', 'public']}).context['counts']['total'], 3)

    def test_empty_and_invalid_filters_do_not_fall_back_to_unrestricted_data(self):
        response = self.view(self.partner, {'category': 'overseas'})
        self.assertEqual(response.context['counts']['total'], 0)
        self.assertContains(response, '표시할 고객사가 없습니다')
        self.assertContains(response, '필터 모두 해제')
        for query in [{'products': [str(uuid4())]}, {'category': 'bad'}, {'category': ['public', 'bad']}, {'products': ['bad']}]:
            response = self.view(self.partner, query)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.context['counts']['total'], 0)
            self.assertEqual(response.context['page'].paginator.count, 0)

    def test_category_sections_include_private_only_counts_without_private_cards(self):
        response = self.view(self.partner)
        groups = response.context['list_groups']
        self.assertEqual([g['code'] for g in groups], ['public', 'local', 'private'])
        private = groups[-1]
        self.assertEqual((private['count'], private['private_count'], private['items']), (1, 1, []))
        self.assertContains(response, '비공개 1곳 포함')
        self.assertNotContains(response, 'count-secondary')
        self.assertNotContains(response, '>실적 현황<')
        self.assertContains(response, '<title>납품현황 · GITSN</title>', html=True)
        self.assertNotContains(response, 'SECRET_TARGET_SENTINEL')
        public = groups[0]
        self.assertEqual(public['count'], 2)  # Listed but uncounted site is not a third customer.
        self.assertEqual(len(public['items']), 3)

    def test_selected_products_emphasized_other_products_subdued_and_unrelated_excluded(self):
        s = Product.objects.create(code='portal-s', name='가상 S', marker='S')
        self.contract(self.public, s, 1)
        unrelated = self.customer('S_ONLY_SENTINEL', True, 'education')
        self.contract(unrelated, s, 1)
        response = self.view(self.partner, {'products': [str(self.c.pk), str(self.i.pk)]})
        self.assertEqual(response.context['counts']['total'], 4)
        self.assertNotContains(response, 'S_ONLY_SENTINEL')
        public = next(row for row in response.context['page'] if row['id'] == str(self.public.pk))
        self.assertEqual({p['id'] for p in public['products'] if p['emphasized']}, {str(self.c.pk), str(self.i.pk)})
        self.assertEqual({p['id'] for p in public['products'] if p['subdued']}, {str(s.pk)})
        site = next(row for row in response.context['page'] if row['kind'] == 'site')
        self.assertEqual([p['id'] for p in site['products']], [str(self.c.pk)])
        self.assertContains(response, 'product-mark is-selected')
        self.assertContains(response, 'product-mark is-subdued')

    def test_name_search_narrows_the_list_but_never_counts_or_print_links(self):
        response = self.view(self.partner, {'q': '단일'})
        self.assertEqual(response.context['counts']['total'], 4)
        self.assertEqual(response.context['page'].paginator.count, 1)
        self.assertContains(response, '단일 제품 가상 기관')
        self.assertNotIn('q=', response.context['print_query'])
        self.assertIn('q=', response.context['filter_query'])
        # A partner cannot probe private names: the counts stay identical and nothing private renders.
        probe = self.view(self.partner, {'q': 'SECRET'})
        self.assertEqual(probe.context['counts']['total'], 4)
        self.assertEqual(probe.context['counts']['private'], 1)
        self.assertEqual(probe.context['page'].paginator.count, 0)
        self.assertNotContains(probe, 'SECRET_TARGET_SENTINEL')
        self.assertContains(probe, '모두 해제')

    def test_category_tabs_toggle_several_categories_and_keep_the_product_filter(self):
        response = self.view(self.employee, {'category': ['local', 'public'], 'products': [str(self.c.pk)]})
        self.assertEqual(response.context['counts']['total'], 3)
        tabs = {tab['code']: tab for tab in response.context['category_tabs']}
        self.assertTrue(tabs['local']['active'] and tabs['public']['active'] and not tabs['']['active'])
        self.assertNotIn('category=local', tabs['local']['url'])
        self.assertIn('category=public', tabs['local']['url'])
        self.assertIn(f'products={self.c.pk}', tabs['local']['url'])
        self.assertIn('category=education', tabs['education']['url'])
        self.assertEqual(tabs['']['url'], f'/performance/?products={self.c.pk}')
        # 2026-10-22 형우: 요약의 분류 칸이 버튼이 되어(분류 탭 대신) 분류를 골라도 계속 보인다.
        self.assertTrue(response.context['show_category_strip'])
        self.assertTrue(self.view(self.employee).context['show_category_strip'])
        chips = {chip['id']: chip for chip in response.context['product_chips']}
        self.assertTrue(chips[str(self.c.pk)]['active'])
        self.assertNotIn('products=', chips[str(self.c.pk)]['url'])
        self.assertIn('category=local', chips[str(self.i.pk)]['url'])

    def test_no_pages_all_rows_on_one_screen_and_sections_fold_only_in_full_view(self):
        # 2026-10-22 형우: 페이지를 없앴다(기준 변경 이유: 끝 페이지까지 '다음'을 여러 번 눌러야 했음).
        for index in range(26):
            customer = self.customer(f'중앙 가상 기관 {index:02}', True, 'central')
            self.contract(customer, self.c, 1)
        response = self.view(self.employee, {'page': 2})
        groups = response.context['list_groups']
        self.assertEqual(groups[0]['code'], 'central')
        self.assertFalse(groups[0]['continued'])
        self.assertEqual(groups[0]['count'], 26)
        self.assertEqual(len(groups[0]['items']), 26)
        self.assertEqual(response.context['counts']['total'], 30)
        self.assertNotContains(response, '— 계속')
        self.assertNotContains(response, 'class="pagination"')
        self.assertTrue(response.context['collapse_sections'])
        self.assertContains(response, 'data-section-more')
        picked = self.view(self.employee, {'category': 'central'})
        self.assertFalse(picked.context['collapse_sections'])
        self.assertNotContains(picked, 'data-section-more')
        self.assertFalse(self.view(self.employee, {'q': '중앙'}).context['collapse_sections'])

    def test_ending_one_product_contract_changes_current_filters_not_history(self):
        self.secret_i.is_active = False
        self.secret_i.save()
        response = self.view(self.partner, {'products': [str(self.c.pk), str(self.i.pk)]})
        self.assertEqual(response.context['counts']['total'], 4)
        self.assertEqual(response.context['counts']['private'], 1)
        only_i = self.view(self.partner, {'products': [str(self.i.pk)]})
        self.assertEqual(only_i.context['counts']['total'], 1)
        self.assertEqual(only_i.context['counts']['private'], 0)
        self.assertEqual(self.view(self.partner).context['counts']['total'], 4)
        self.secret_c.is_active = False
        self.secret_c.save()
        self.assertEqual(self.view(self.partner).context['counts']['total'], 3)
        self.assertTrue(ContractProduct.objects.filter(contract=self.secret_c).exists())

    def test_partner_cannot_open_any_detail_or_account_route_even_with_manager_permission(self):
        self.partner.user_permissions.add(Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery'))
        self.client.force_login(self.partner)
        urls = [reverse('employee-customer', args=[self.public.pk]), reverse('employee-customer', args=[self.secret.pk]),
                reverse('employee-contract', args=[self.public_c.pk]), reverse('employee-site', args=[self.site.pk]),
                '/planning/accounts/', '/planning/accounts/new/', reverse('account-edit', args=[self.employee.pk]),
                reverse('account-password', args=[self.employee.pk]), '/planning/customers/new/']
        for url in urls:
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_employee_details_include_quantities_but_never_mail_sources_or_management(self):
        self.client.force_login(self.employee)
        customer = self.client.get(reverse('employee-customer', args=[self.public.pk]))
        self.assertEqual(customer.context['total_quantity'], 15)
        for url in [reverse('employee-contract', args=[self.public_c.pk]), reverse('employee-customer', args=[self.secret.pk]), reverse('employee-site', args=[self.site.pk])]:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            for text in ['SOURCE_SUBJECT_SENTINEL', 'SOURCE_SENDER_SENTINEL', 'PRIVATE_MEMO_SENTINEL', 'source_email', '/planning/accounts/', '계약 수정', '계약 종료</a>']:
                self.assertNotContains(response, text)
        self.assertEqual(self.client.post(reverse('employee-customer', args=[self.public.pk]), {}).status_code, 405)
        self.assertEqual(self.client.get('/planning/accounts/').status_code, 403)

    def test_anonymous_missing_profile_and_inactive_accounts_are_denied(self):
        self.assertRedirects(self.client.get('/performance/'), '/login/?next=/performance/')
        unassigned = get_user_model().objects.create_user('no-profile', password='LocalPortalOnly!73')
        response = self.client.post('/login/', {'username': unassigned.username, 'password': 'LocalPortalOnly!73'})
        self.assertContains(response, '열람 권한이 설정된 계정')
        self.employee.is_active = False
        self.employee.save()
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get('/performance/').status_code, 302)

    def test_logos_follow_current_public_policy_and_hide_file_paths(self):
        self.public.logo.save('public.png', image_upload())
        self.secret.logo.save('secret.png', image_upload())
        self.client.force_login(self.partner)
        url = reverse('performance-logo', args=['customer', self.public.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertTrue(b''.join(response.streaming_content).startswith(b'\x89PNG'))
        self.assertNotIn('public.png', response['Content-Disposition'])
        self.assertEqual(self.client.get(reverse('performance-logo', args=['customer', self.secret.pk])).status_code, 404)
        self.public.partner_public = False
        self.public.save()
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.employee)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        b''.join(response.streaming_content)

    def test_seventy_public_thirty_private_counts_and_pagination_keep_same_filter(self):
        # Use a category absent from the initial fixture; do not modify existing relations.
        for index in range(100):
            customer = self.customer(f'교육 가상 기관 {index:03}', index < 70, 'education')
            self.contract(customer, self.c, 1)
        query = {'category': 'education', 'products': [str(self.c.pk)]}
        for user in [self.employee, self.partner]:
            response = self.view(user, query)
            self.assertEqual(response.context['counts']['total'], 100)
            self.assertEqual(response.context['counts']['private'], 30)
            self.assertContains(response, 'category=education')
            self.assertContains(response, str(self.c.pk))
        for page in [1, 2, 3]:
            response = self.view(self.partner, {**query, 'page': page})
            self.assertEqual(response.context['page'].paginator.count, 70)
            self.assertEqual(response.context['counts']['total'], 100)
            for index in range(70, 100):
                self.assertNotContains(response, f'교육 가상 기관 {index:03}')

    def test_manager_can_create_account_without_echoing_or_storing_plain_password(self):
        self.client.force_login(self.manager)
        data = self.account_data(role='partner')
        response = self.client.post('/planning/accounts/new/', data)
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username=data['username'])
        self.assertTrue(user.check_password(data['password1']))
        self.assertNotEqual(user.password, data['password1'])
        self.assertEqual(user.delivery_access.audience, 'partner')
        self.assertFalse(user.has_perm('delivery.manage_delivery'))
        for url in ['/planning/accounts/', response.url, reverse('account-password', args=[user.pk])]:
            page = self.client.get(url)
            self.assertNotContains(page, data['password1'])
            self.assertNotContains(page, user.password)
        response = self.client.post('/planning/accounts/new/', self.account_data(username='NEW-ACCOUNT'))
        self.assertContains(response, '이미 사용 중인 아이디')

    def test_account_edit_checks_stale_revision_and_prevents_self_lockout(self):
        self.client.force_login(self.manager)
        revision = account_revision(self.employee)
        self.employee.first_name = '다른 작업 변경'
        self.employee.save()
        response = self.client.post(reverse('account-edit', args=[self.employee.pk]), {'first_name': '덮어쓰기', 'role': 'partner', 'is_active': 'on', 'revision': revision})
        self.assertContains(response, '다른 작업에서 계정이 수정')
        self.employee.refresh_from_db()
        self.assertEqual(self.employee.first_name, '다른 작업 변경')
        for data in [{'role': 'partner', 'is_active': 'on'}, {'role': 'manager'}]:
            response = self.client.post(reverse('account-edit', args=[self.manager.pk]), {**data, 'revision': account_revision(self.manager)})
            self.assertContains(response, '본인 계정')
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)
        self.assertTrue(self.manager.has_perm('delivery.manage_delivery'))

    def test_account_role_change_and_disable_apply_to_existing_session(self):
        employee_client = Client()
        employee_client.force_login(self.employee)
        self.client.force_login(self.manager)
        url = reverse('account-edit', args=[self.employee.pk])
        self.client.post(url, {'role': 'partner', 'is_active': 'on', 'revision': account_revision(self.employee)})
        self.assertEqual(employee_client.get(reverse('employee-customer', args=[self.public.pk])).status_code, 403)
        self.assertNotContains(employee_client.get('/performance/'), 'SECRET_TARGET_SENTINEL')
        self.employee.refresh_from_db()
        self.client.post(url, {'role': 'partner', 'revision': account_revision(self.employee)})
        self.assertEqual(employee_client.get('/performance/').status_code, 302)

    def test_password_reset_invalidates_old_sessions_and_password(self):
        previous = Client()
        previous.force_login(self.partner)
        self.client.force_login(self.manager)
        response = self.client.post(reverse('account-password', args=[self.partner.pk]), {'new_password1': 'ResetLocalExample!75', 'new_password2': 'ResetLocalExample!75', 'revision': account_revision(self.partner)})
        self.assertEqual(response.status_code, 302)
        self.partner.refresh_from_db()
        self.assertTrue(self.partner.check_password('ResetLocalExample!75'))
        self.assertFalse(self.partner.check_password('LocalPortalOnly!73'))
        self.assertEqual(previous.get('/performance/').status_code, 302)

    def test_own_password_reset_requires_relogin_and_csrf_is_required(self):
        self.client.force_login(self.manager)
        url = reverse('account-password', args=[self.manager.pk])
        response = self.client.post(url, {'new_password1': 'OwnResetExample!76', 'new_password2': 'OwnResetExample!76', 'revision': account_revision(self.manager)})
        self.assertRedirects(response, '/login/')
        self.assertEqual(self.client.get('/planning/accounts/').status_code, 302)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.employee)
        self.assertEqual(secure.post('/planning/accounts/new/', self.account_data()).status_code, 403)
        self.manager.refresh_from_db()
        secure.force_login(self.manager)
        secure.get('/planning/accounts/new/')
        self.assertEqual(secure.post('/planning/accounts/new/', self.account_data()).status_code, 403)
        self.assertEqual(secure.post('/planning/accounts/new/', self.account_data(csrfmiddlewaretoken=secure.cookies['csrftoken'].value)).status_code, 302)

    def test_account_creation_is_atomic_and_direct_service_requires_manager(self):
        with self.assertRaises(PermissionDenied):
            create_account(self.partner, self.account_data())
        with self.assertRaises(ValidationError):
            create_account(self.manager, self.account_data(role='invalid'))
        self.assertFalse(get_user_model().objects.filter(username='new-account').exists())
