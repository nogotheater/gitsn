"""Runs on a separate Django PostgreSQL test database, never the local customer DB."""
from tempfile import TemporaryDirectory
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from delivery.models import (
    Customer, Organization, Contract, ContractProduct, InstallationSite,
    Product, SitePresentation, SiteProductSelection, UserAccessProfile,
)
from delivery.services.audience_performance import current_performance_payload
from delivery.services.current_performance import customer_current_quantities, site_current_product_ids
from .test_planning_forms import image_upload


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PlanningHttpScenarios(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.manager = User.objects.create_user('test-planning', password='LocalTestOnly!27')
        UserAccessProfile.objects.create(user=cls.manager, audience='employee')
        cls.manager.user_permissions.add(Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery'))
        cls.employee = User.objects.create_user('test-sales', password='LocalTestOnly!27')
        cls.partner = User.objects.create_user('test-partner', password='LocalTestOnly!27')
        UserAccessProfile.objects.create(user=cls.employee, audience='employee')
        UserAccessProfile.objects.create(user=cls.partner, audience='partner')
        cls.c = Product.objects.create(code='test-c', name='가상 제품 C', marker='C')
        cls.i = Product.objects.create(code='test-i', name='가상 제품 I', marker='I')

    def setUp(self):
        self.client.force_login(self.manager)
        folder = self.enterContext(TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=folder))

    def make_customer(self, name='가상 고객사'):
        return Customer.objects.create(organization=Organization.objects.create(official_name=name), category='public', partner_public=True)

    def customer_data(self, **changes):
        return {**{'official_name': '새 가상 고객사', 'category': 'public', 'region': '', 'display_as': 'customer',
                   'partner_public': 'default', 'include_in_total': 'on', 'show_in_list': 'on', 'memo': ''}, **changes}

    def contract_data(self, quantities=None, sites=False, **changes):
        quantities = quantities or [(self.c, 10), (self.i, 5)]
        data = {'party_mode': 'customer', 'is_active': 'active', 'contract_date': '',
                'source_email_subject': '', 'source_email_received_on': '', 'source_email_sender': '',
                'products-TOTAL_FORMS': str(len(quantities)), 'products-INITIAL_FORMS': '0',
                'products-MIN_NUM_FORMS': '1', 'products-MAX_NUM_FORMS': '1000',
                'sites-TOTAL_FORMS': '1' if sites else '0', 'sites-INITIAL_FORMS': '0',
                'sites-MIN_NUM_FORMS': '0', 'sites-MAX_NUM_FORMS': '1000'}
        for index, (product, quantity) in enumerate(quantities):
            data[f'products-{index}-product'] = str(product.pk)
            data[f'products-{index}-quantity'] = str(quantity)
        if sites:
            data.update({'sites-0-new_site_name': '가상 설치 장소', 'sites-0-products': [str(self.c.pk)],
                         'sites-0-show_in_list': 'on', 'sites-0-display_as': 'site', 'sites-0-partner_public': 'default',
                         'sites-0-category': '', 'sites-0-region': ''})
        return {**data, **changes}

    def post_contract(self, customer, data=None):
        response = self.client.post(reverse('planning-contract-new', args=[customer.pk]), data or self.contract_data())
        self.assertEqual(response.status_code, 302, str(response.context and response.context['form'].errors))
        return customer.contracts.latest('created_at')

    def test_manager_pages_render_and_customer_can_be_saved_without_optional_fields(self):
        response = self.client.get(reverse('planning-customer-new'))
        self.assertContains(response, '고객사 등록')
        response = self.client.post(reverse('planning-customer-new'), self.customer_data())
        self.assertEqual(response.status_code, 302)
        customer = Customer.objects.get()
        self.assertFalse(bool(customer.logo))
        self.assertEqual(customer.memo, '')
        response = self.client.get(response.url)
        self.assertContains(response, customer.organization.official_name)
        self.assertContains(response, '계약 추가')

    def test_region_and_duplicate_name_validation_keep_input_without_partial_customer(self):
        response = self.client.post(reverse('planning-customer-new'), self.customer_data(category='local'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '지역을 선택해 주세요')
        self.assertEqual(Customer.objects.count(), 0)
        self.make_customer('새 가상 고객사')
        response = self.client.post(reverse('planning-customer-new'), self.customer_data())
        self.assertContains(response, '같은 공식 명칭')
        self.assertEqual(Customer.objects.count(), 1)

    def test_new_private_customer_can_be_explicitly_public_but_category_change_resets(self):
        self.client.post(reverse('planning-customer-new'), self.customer_data(category='private', partner_public='public'))
        customer = Customer.objects.get()
        self.assertTrue(customer.partner_public)
        response = self.client.post(reverse('planning-customer-edit', args=[customer.pk]),
                                    self.customer_data(category='public', partner_public='private', revision=customer.updated_at.isoformat()))
        self.assertEqual(response.status_code, 302)
        customer.refresh_from_db()
        self.assertTrue(customer.partner_public)

    def test_contract_sites_and_optional_source_save_with_correct_quantities_and_products(self):
        customer = self.make_customer()
        contract = self.post_contract(customer, self.contract_data(sites=True))
        contract.refresh_from_db()
        self.assertIsNone(contract.contract_date)
        self.assertEqual(contract.source_email_subject, '')
        self.assertEqual(customer_current_quantities(customer.pk), {str(self.c.pk): 10, str(self.i.pk): 5})
        site = InstallationSite.objects.get()
        self.assertEqual(set(site_current_product_ids(site.pk)), {self.c.pk})
        presentation = SitePresentation.objects.get()
        self.assertFalse(presentation.include_in_total)
        self.assertEqual(current_performance_payload(self.manager)['counts']['total'], 1)
        self.assertContains(self.client.get(reverse('planning-contract-detail', args=[contract.pk])), '합계')
        self.assertContains(self.client.get(reverse('planning-contract-edit', args=[customer.pk, contract.pk])), '계약 수정')
        self.assertContains(self.client.get(reverse('planning-site-edit', args=[site.pk])), '설치 장소 표시 설정')

    def test_invalid_quantity_keeps_form_values_and_writes_no_contract(self):
        customer = self.make_customer()
        response = self.client.post(reverse('planning-contract-new', args=[customer.pk]),
                                    self.contract_data([(self.c, '1.5')], source_email_subject='입력 유지 확인'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '1 이상의 정수')
        self.assertContains(response, '입력 유지 확인')
        self.assertContains(response, 'value="1.5"')
        self.assertEqual(Contract.objects.count(), 0)

    def test_duplicate_product_and_out_of_contract_site_product_are_rejected(self):
        customer = self.make_customer()
        response = self.client.post(reverse('planning-contract-new', args=[customer.pk]), self.contract_data([(self.c, 1), (self.c, 2)]))
        self.assertContains(response, '같은 제품은 한 줄')
        response = self.client.post(reverse('planning-contract-new', args=[customer.pk]), self.contract_data([(self.i, 1)], sites=True))
        self.assertContains(response, '이 계약에 등록한 제품')
        self.assertEqual(Contract.objects.count(), 0)
        self.assertEqual(InstallationSite.objects.count(), 0)

    def test_error_after_starting_a_save_rolls_back_contract_lines_and_place(self):
        customer = self.make_customer()
        response = self.client.post(reverse('planning-contract-new', args=[customer.pk]),
                                    self.contract_data(sites=True, **{'sites-0-category': 'local'}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Contract.objects.count(), 0)
        self.assertEqual(ContractProduct.objects.count(), 0)
        self.assertEqual(InstallationSite.objects.count(), 0)

    def test_contract_edit_can_remove_product_after_place_assignment_is_changed(self):
        customer = self.make_customer()
        contract = self.post_contract(customer, self.contract_data(sites=True))
        site = InstallationSite.objects.get()
        data = self.contract_data([(self.i, 5)], sites=True, revision=contract.updated_at.isoformat(),
                                  **{'sites-0-existing_site': str(site.pk), 'sites-0-new_site_name': '', 'sites-0-products': [str(self.i.pk)]})
        response = self.client.post(reverse('planning-contract-edit', args=[customer.pk, contract.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(customer_current_quantities(customer.pk), {str(self.i.pk): 5})
        self.assertEqual(set(site_current_product_ids(site.pk)), {self.i.pk})
        self.assertEqual(SiteProductSelection.objects.count(), 1)

    def test_partial_then_full_contract_termination_preserves_history(self):
        customer = self.make_customer()
        first = self.post_contract(customer, self.contract_data([(self.c, 10)]))
        second = self.post_contract(customer, self.contract_data([(self.c, 5)]))
        self.assertEqual(customer_current_quantities(customer.pk), {str(self.c.pk): 15})
        self.assertContains(self.client.get(reverse('planning-contract-end', args=[first.pk])), '이 계약을 종료할까요')
        self.client.post(reverse('planning-contract-end', args=[first.pk]), {'revision': first.updated_at.isoformat()})
        self.assertEqual(customer_current_quantities(customer.pk), {str(self.c.pk): 5})
        self.assertEqual(current_performance_payload(self.manager)['counts']['total'], 1)
        self.client.post(reverse('planning-contract-end', args=[second.pk]), {'revision': second.updated_at.isoformat()})
        self.assertEqual(current_performance_payload(self.manager)['counts']['total'], 0)
        self.assertEqual(Contract.objects.count(), 2)
        self.assertEqual(sum(ContractProduct.objects.values_list('quantity', flat=True)), 15)

    def test_stale_edit_does_not_overwrite_a_newer_customer(self):
        customer = self.make_customer()
        previous = customer.updated_at.isoformat()
        customer.memo = '새 변경 내용'
        customer.save()
        response = self.client.post(reverse('planning-customer-edit', args=[customer.pk]), self.customer_data(revision=previous))
        self.assertContains(response, '다른 작업에서 내용이 수정')
        customer.refresh_from_db()
        self.assertEqual(customer.memo, '새 변경 내용')

    def test_employee_partner_and_anonymous_cannot_read_or_post_planning_data(self):
        key = uuid4()
        urls = ['/planning/', '/planning/customers/new/', f'/planning/customers/{key}/',
                f'/planning/customers/{key}/edit/', f'/planning/customers/{key}/contracts/new/',
                f'/planning/customers/{key}/contracts/{key}/edit/',
                f'/planning/contracts/{key}/', f'/planning/contracts/{key}/end/',
                f'/planning/places/{key}/edit/', f'/planning/logos/customer/{key}/', '/planning/products/new/',
                f'/planning/products/{key}/edit/', f'/planning/customers/{key}/duplicates/',
                f'/planning/customers/{key}/duplicates/review/']
        for user in [self.employee, self.partner]:
            self.client.force_login(user)
            for url in urls:
                with self.subTest(user=user.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 403)
                    self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.client.logout()
        self.assertRedirects(self.client.get('/planning/'), '/login/?next=/planning/')
        self.assertEqual(Customer.objects.count(), 0)

    def test_csrf_required_and_good_token_can_submit(self):
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.manager)
        secure.get('/planning/customers/new/')
        self.assertEqual(secure.post('/planning/customers/new/', self.customer_data()).status_code, 403)
        data = self.customer_data(csrfmiddlewaretoken=secure.cookies['csrftoken'].value)
        self.assertEqual(secure.post('/planning/customers/new/', data).status_code, 302)

    def test_login_accepts_partner_without_management_access_and_rejects_external_redirect(self):
        self.client.logout()
        response = self.client.post('/login/', {'username': self.partner.username, 'password': 'LocalTestOnly!27'})
        self.assertRedirects(response, '/performance/')
        self.assertEqual(self.client.get('/planning/').status_code, 403)
        self.client.logout()
        response = self.client.post('/login/', {'username': self.manager.username, 'password': 'LocalTestOnly!27', 'next': 'https://example.org/'})
        self.assertRedirects(response, '/planning/')
        self.assertEqual(self.client.get('/logout/').status_code, 405)

    def test_logo_optional_upload_validated_and_only_manager_can_download(self):
        response = self.client.post('/planning/customers/new/', self.customer_data(logo=image_upload()))
        self.assertEqual(response.status_code, 302)
        customer = Customer.objects.get()
        url = reverse('planning-logo', args=['customer', customer.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/png')
        # Consume Django's streaming wrapper so its normal cleanup preserves the
        # enclosing TestCase transaction instead of closing PostgreSQL early.
        self.assertTrue(b''.join(response.streaming_content).startswith(b'\x89PNG\r\n\x1a\n'))
        self.assertTrue(response.closed)
        self.assertEqual(Customer.objects.count(), 1)
        self.client.force_login(self.partner)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_customer_search_and_names_are_escaped(self):
        self.make_customer('<script>alert(1)</script>')
        response = self.client.get('/planning/', {'q': '<script>'})
        self.assertContains(response, '&lt;script&gt;')
        self.assertNotContains(response, '<script>alert(1)</script>')

    def test_product_creation_is_manager_only_and_rejects_duplicate_code(self):
        self.assertContains(self.client.get('/planning/products/new/'), '제품 관리')
        data = {'code': 'Alpha-X', 'name': '가상 추가 제품', 'marker': 'X', 'color': '#0474D4'}
        self.assertEqual(self.client.post('/planning/products/new/', data).status_code, 302)
        response = self.client.post('/planning/products/new/', data)
        self.assertContains(response, '이미 등록된 제품 코드')
        self.assertEqual(Product.objects.filter(code='Alpha-X').count(), 1)


    def test_unused_product_can_be_deleted_from_the_catalog_but_a_contracted_one_cannot(self):
        spare = Product.objects.create(code='test-spare', name='가상 여분 제품', marker='S')
        page = self.client.get('/planning/products/new/')
        self.assertContains(page, reverse('planning-product-delete', args=[spare.pk]))
        self.assertContains(page, 'data-confirm')
        self.assertEqual(self.client.get(reverse('planning-product-delete', args=[spare.pk])).status_code, 405)
        response = self.client.post(reverse('planning-product-delete', args=[spare.pk]), follow=True)
        self.assertContains(response, '제품을 삭제했습니다')
        self.assertContains(response, 'notice success')
        self.assertFalse(Product.objects.filter(pk=spare.pk).exists())
        customer = self.make_customer()
        self.post_contract(customer, self.contract_data([(self.c, 2)]))
        response = self.client.post(reverse('planning-product-delete', args=[self.c.pk]), follow=True)
        self.assertContains(response, '계약 1건에서 쓰이고 있어 삭제할 수 없습니다')
        self.assertContains(response, 'notice error')
        self.assertTrue(Product.objects.filter(pk=self.c.pk).exists())
        self.assertEqual(current_performance_payload(self.manager)['counts']['total'], 1)
        self.client.force_login(self.employee)
        self.assertIn(self.client.post(reverse('planning-product-delete', args=[self.i.pk])).status_code, [302, 403])
        self.assertTrue(Product.objects.filter(pk=self.i.pk).exists())
    def test_existing_physical_site_can_receive_settings_without_a_get_write(self):
        site = InstallationSite.objects.create(official_name='기존 가상 장소')
        url = reverse('planning-site-edit', args=[site.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(SitePresentation.objects.count(), 0)
        data = self.customer_data(official_name=site.official_name, display_as='site')
        data.pop('include_in_total')
        data.pop('show_in_list')
        self.assertEqual(self.client.post(url, data).status_code, 302)
        presentation = SitePresentation.objects.get()
        self.assertFalse(presentation.include_in_total)
        self.assertFalse(presentation.show_in_list)

    def test_product_marker_color_can_be_changed_without_changing_customer_count(self):
        customer = self.make_customer()
        self.post_contract(customer, self.contract_data([(self.c, 2)]))
        data = {'code': self.c.code, 'name': self.c.name, 'marker': 'C', 'color': '#1A8CF7', 'revision': self.c.updated_at.isoformat()}
        response = self.client.post(reverse('planning-product-edit', args=[self.c.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.c.refresh_from_db()
        self.assertEqual(self.c.color, '#1A8CF7')
        self.assertEqual(current_performance_payload(self.manager)['counts']['total'], 1)

    def merge_data(self, primary, duplicate_ids, rows, **changes):
        data = {**self.customer_data(official_name=str(primary), revision=primary.updated_at.isoformat()), **changes}
        data['duplicate_ids'] = [str(value) for value in duplicate_ids]
        # Mirrors what the review page's own GET render sends: these rows are the duplicate's
        # existing contracts, not blank extra rows, so INITIAL_FORMS equals the row count.
        data.update({'form-TOTAL_FORMS': str(len(rows)), 'form-INITIAL_FORMS': str(len(rows)), 'form-MIN_NUM_FORMS': '0', 'form-MAX_NUM_FORMS': '1000'})
        for index, (contract, action, target) in enumerate(rows):
            data[f'form-{index}-contract_id'] = str(contract.pk)
            data[f'form-{index}-action'] = action
            if target:
                data[f'form-{index}-superseded_by'] = str(target.pk)
        return data

    def test_duplicate_search_and_review_render_the_candidate_and_its_contracts(self):
        primary = self.make_customer('유지할 가상 고객사')
        duplicate = self.make_customer('중복 가상 고객사')
        response = self.client.get(reverse('planning-duplicate-search', args=[primary.pk]))
        self.assertContains(response, '중복 고객사 선택')
        self.assertContains(response, str(duplicate))
        response = self.client.get(reverse('planning-duplicate-review', args=[primary.pk]), {'d': str(duplicate.pk)})
        self.assertContains(response, '중복 통합 검토')
        self.assertContains(response, str(duplicate))

    def test_merge_includes_two_different_contracts_and_sums_to_15(self):
        primary = self.make_customer('유지할 가상 고객사')
        duplicate = self.make_customer('중복 가상 고객사')
        self.post_contract(primary, self.contract_data([(self.c, 10)]))
        moving = self.post_contract(duplicate, self.contract_data([(self.c, 5)]))
        data = self.merge_data(primary, [duplicate.pk], [(moving, 'include', None)])
        response = self.client.post(reverse('planning-duplicate-review', args=[primary.pk]), data)
        self.assertEqual(response.status_code, 302,
                         str(response.context and (response.context['presentation_form'].errors, response.context['contract_formset'].errors)))
        self.assertEqual(customer_current_quantities(primary.pk), {str(self.c.pk): 15})
        moving.refresh_from_db()
        self.assertEqual(moving.customer_id, primary.pk)
        self.assertTrue(moving.is_active)
        duplicate.refresh_from_db()
        self.assertEqual(duplicate.merged_into_id, primary.pk)
        self.assertIsNotNone(duplicate.merged_at)
        self.assertFalse(duplicate.show_in_list)
        self.assertFalse(duplicate.include_in_total)

    def test_merge_excludes_a_duplicate_connection_of_the_same_10_and_does_not_double_count(self):
        primary = self.make_customer('유지할 가상 고객사')
        duplicate = self.make_customer('중복 가상 고객사')
        kept = self.post_contract(primary, self.contract_data([(self.c, 10)]))
        duplicate_copy = self.post_contract(duplicate, self.contract_data([(self.c, 10)]))
        data = self.merge_data(primary, [duplicate.pk], [(duplicate_copy, 'exclude', kept)])
        response = self.client.post(reverse('planning-duplicate-review', args=[primary.pk]), data)
        self.assertEqual(response.status_code, 302,
                         str(response.context and (response.context['presentation_form'].errors, response.context['contract_formset'].errors)))
        self.assertEqual(customer_current_quantities(primary.pk), {str(self.c.pk): 10})
        duplicate_copy.refresh_from_db()
        self.assertFalse(duplicate_copy.is_active)
        self.assertEqual(duplicate_copy.superseded_by_id, kept.pk)
        self.assertEqual(duplicate_copy.customer_id, primary.pk)

    def test_merge_rejects_exclude_without_a_surviving_contract_and_changes_nothing(self):
        primary = self.make_customer('유지할 가상 고객사')
        duplicate = self.make_customer('중복 가상 고객사')
        self.post_contract(primary, self.contract_data([(self.c, 10)]))
        moving = self.post_contract(duplicate, self.contract_data([(self.c, 10)]))
        previous_updated = primary.updated_at
        data = self.merge_data(primary, [duplicate.pk], [(moving, 'exclude', None)])
        response = self.client.post(reverse('planning-duplicate-review', args=[primary.pk]), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '동일한 기존 계약을 선택')
        moving.refresh_from_db()
        self.assertEqual(moving.customer_id, duplicate.pk)
        self.assertTrue(moving.is_active)
        duplicate.refresh_from_db()
        self.assertIsNone(duplicate.merged_into_id)
        primary.refresh_from_db()
        self.assertEqual(primary.updated_at, previous_updated)

    def test_merge_failing_midway_rolls_back_the_already_applied_name_change(self):
        primary = self.make_customer('유지할 가상 고객사')
        duplicate = self.make_customer('중복 가상 고객사')
        self.post_contract(duplicate, self.contract_data([(self.c, 10)]))
        self.post_contract(duplicate, self.contract_data([(self.i, 5)]))
        # Submits only one of the duplicate's two active contracts, as if a second contract
        # were added to it after this merge screen was first loaded.
        first_only = Contract.objects.filter(customer=duplicate).order_by('created_at')[:1]
        data = self.merge_data(primary, [duplicate.pk], [(contract, 'include', None) for contract in first_only],
                               official_name='새로 바뀐 이름')
        response = self.client.post(reverse('planning-duplicate-review', args=[primary.pk]), data)
        self.assertEqual(response.status_code, 200)
        primary.refresh_from_db()
        primary.organization.refresh_from_db()
        self.assertEqual(primary.organization.official_name, '유지할 가상 고객사')
        self.assertEqual(Contract.objects.filter(customer=duplicate).count(), 2)
        self.assertEqual(Contract.objects.filter(customer=primary).count(), 0)
        duplicate.refresh_from_db()
        self.assertIsNone(duplicate.merged_into_id)

    def test_merged_customer_is_hidden_and_blocks_further_edits_and_new_contracts(self):
        primary = self.make_customer('유지할 가상 고객사')
        duplicate = self.make_customer('중복 가상 고객사')
        data = self.merge_data(primary, [duplicate.pk], [])
        response = self.client.post(reverse('planning-duplicate-review', args=[primary.pk]), data)
        self.assertEqual(response.status_code, 302)
        self.assertNotContains(self.client.get(reverse('planning-home')), '중복 가상 고객사')
        self.assertContains(self.client.get(reverse('planning-customer-detail', args=[duplicate.pk])), '통합되었습니다')
        self.assertRedirects(self.client.get(reverse('planning-customer-edit', args=[duplicate.pk])),
                             reverse('planning-customer-detail', args=[primary.pk]))
        self.assertRedirects(self.client.get(reverse('planning-contract-new', args=[duplicate.pk])),
                             reverse('planning-customer-detail', args=[primary.pk]))
