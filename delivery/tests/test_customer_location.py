"""4단계: 고객사 소재지·기관 유형 입력(2026-10-22 형우 확정).

- 지자체·의회에서만 입력, 명칭으로 바로 제안(guess_location), 기관 유형은 제안 + 수정 가능.
- 소재지를 고르면 지역(권역)이 따라간다. 다른 분류로 저장해도 기존 소재지는 유지.
- 소재지가 비면 상세·목록에 '소재지 미입력' 표시.
"""
import os
from tempfile import TemporaryDirectory
from unittest import skipUnless
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from playwright.sync_api import sync_playwright, expect
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from delivery.domain import admin_areas as aa
from delivery.domain.locations import parse_location
from delivery.forms import PresentationForm
from delivery.models import Customer, Organization, UserAccessProfile
from delivery.services.customer_location import join_location, split_location, suggestion

CHEONAN = parse_location('충남 천안시')
SEJONG = parse_location('세종')


class LocationHelpers(SimpleTestCase):
    def test_split_and_join_round_trip(self):
        for code in [CHEONAN, '41', SEJONG, '']:
            self.assertEqual(join_location(*split_location(code)), code)
        self.assertEqual(split_location(CHEONAN), ('44', CHEONAN))
        self.assertEqual(split_location(SEJONG), ('36', ''))

    def test_suggestion_uses_name_and_follows_region(self):
        s = suggestion('천안시', 'local', '')
        self.assertEqual((s['label'], s['institution_type'], s['region'], s['sido'], s['unit']),
                         ('충남 천안시', 'admin', 'chungcheong', '44', CHEONAN))
        self.assertEqual(suggestion('천안시의회', 'council')['label'], '충남 천안시')
        ambiguous = suggestion('중구', 'local', '')
        self.assertEqual(ambiguous['location'], '')
        self.assertIn('후보', ambiguous['reason'])
        self.assertEqual(suggestion('천안시', 'public')['location'], '')
        self.assertEqual(suggestion('', 'local')['location'], '')

    def test_site_form_has_no_location_fields(self):
        self.assertNotIn('location_sido', PresentationForm().fields)
        self.assertIn('location_sido', PresentationForm(with_location=True).fields)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CustomerLocationHttp(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.manager = User.objects.create_user('loc-manager', password='LocalLocOnly!31')
        UserAccessProfile.objects.create(user=cls.manager, audience='employee')
        cls.manager.user_permissions.add(Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery'))
        cls.employee = User.objects.create_user('loc-employee', password='LocalLocOnly!31')
        UserAccessProfile.objects.create(user=cls.employee, audience='employee')

    def setUp(self):
        self.client.force_login(self.manager)
        self.enterContext(override_settings(MEDIA_ROOT=self.enterContext(TemporaryDirectory())))

    def data(self, **changes):
        return {**{'official_name': '천안시', 'category': 'local', 'region': 'capital', 'display_as': 'customer',
                   'partner_public': 'default', 'include_in_total': 'on', 'show_in_list': 'on', 'memo': '',
                   'location_sido': '44', 'location_unit': CHEONAN, 'institution_type': 'admin'}, **changes}

    def create(self, **changes):
        response = self.client.post(reverse('planning-customer-new'), self.data(**changes))
        self.assertEqual(response.status_code, 302, response.context and response.context['form'].errors)
        return Customer.objects.get(organization__official_name=changes.get('official_name', '천안시'))

    def test_guess_endpoint_is_manager_only_json(self):
        response = self.client.get(reverse('planning-location-guess'), {'name': '천안시', 'category': 'local'})
        self.assertEqual(response.json()['label'], '충남 천안시')
        self.client.force_login(self.employee)
        self.assertEqual(self.client.get(reverse('planning-location-guess'), {'name': '천안시', 'category': 'local'}).status_code, 403)

    def test_save_stores_location_type_and_region_follows_location(self):
        customer = self.create()
        self.assertEqual((customer.location_code, customer.institution_type, customer.region), (CHEONAN, 'admin', 'chungcheong'))
        detail = self.client.get(reverse('planning-customer-detail', args=[customer.pk]))
        self.assertContains(detail, '소재지 충남 천안시 · 행정기관')
        self.assertNotContains(detail, '소재지 미입력')

    def test_whole_sido_and_one_area_sido(self):
        self.assertEqual(self.create(official_name='경기도', location_sido='41', location_unit='').location_code, '41')
        sejong = self.create(official_name='세종특별자치시', location_sido='36', location_unit='', region='')
        self.assertEqual((sejong.location_code, sejong.region), (SEJONG, 'chungcheong'))

    def test_unit_outside_sido_and_missing_type_are_rejected(self):
        response = self.client.post(reverse('planning-customer-new'), self.data(location_sido='41'))
        self.assertFormError(response.context['form'], 'location_unit', '선택한 시·도 안의 시군구를 골라 주세요.')
        response = self.client.post(reverse('planning-customer-new'), self.data(institution_type=''))
        self.assertFormError(response.context['form'], 'institution_type', '기관 유형을 선택해 주세요.')
        self.assertFalse(Customer.objects.exists())

    def test_blank_location_is_flagged_on_detail_and_list(self):
        customer = self.create(location_sido='', location_unit='', institution_type='admin')
        self.assertEqual((customer.location_code, customer.institution_type, customer.region), ('', '', 'capital'))
        self.assertContains(self.client.get(reverse('planning-customer-detail', args=[customer.pk])), '소재지 미입력')
        self.assertContains(self.client.get(reverse('planning-home')), '소재지 미입력')

    def test_other_category_keeps_existing_location_and_hides_fields_on_list(self):
        customer = self.create()
        edit = self.client.get(reverse('planning-customer-edit', args=[customer.pk]))
        self.assertEqual(edit.context['form'].initial['location_unit'], CHEONAN)
        response = self.client.post(reverse('planning-customer-edit', args=[customer.pk]), self.data(
            category='public', region='', location_sido='', location_unit='', institution_type='',
            revision=customer.updated_at.isoformat()))
        self.assertEqual(response.status_code, 302)
        customer.refresh_from_db()
        self.assertEqual((customer.category, customer.location_code, customer.institution_type), ('public', CHEONAN, 'admin'))
        self.assertNotContains(self.client.get(reverse('planning-home')), '소재지 미입력')

    def test_site_edit_form_has_no_location_fields(self):
        self.assertNotIn('location_sido', PresentationForm(with_location=False).fields)

    def test_customer_form_has_no_list_toggle_and_keeps_saved_value(self):
        # 2026-10-22 형우: 고객사 화면에서 '실적 목록에 표시'를 뺐다. 새 고객사는 표시, 저장된 값은 그대로(설치 장소 화면에는 남음).
        self.assertNotIn('show_in_list', PresentationForm(with_location=True).fields)
        self.assertIn('show_in_list', PresentationForm(with_location=False).fields)
        self.assertNotContains(self.client.get(reverse('planning-customer-new')), '실적 목록에 표시')
        customer = self.create(show_in_list='')
        self.assertTrue(customer.show_in_list)
        Customer.objects.filter(pk=customer.pk).update(show_in_list=False)
        customer.refresh_from_db()
        response = self.client.post(reverse('planning-customer-edit', args=[customer.pk]),
                                    self.data(memo='메모', revision=customer.updated_at.isoformat()))
        self.assertEqual(response.status_code, 302)
        customer.refresh_from_db()
        self.assertFalse(customer.show_in_list)

    def test_region_only_for_local_and_council(self):
        # 2026-10-22 형우: 지역(권역)은 지자체·의회에서만 보이고, 다른 분류로 저장하면 비운다.
        self.assertContains(self.client.get(reverse('planning-customer-new')), 'data-region-field hidden')
        customer = self.create(official_name='가상 공공기관', category='public', region='capital',
                               location_sido='', location_unit='', institution_type='')
        self.assertEqual(customer.region, '')
        edit = self.client.get(reverse('planning-customer-edit', args=[self.create().pk]))
        self.assertNotContains(edit, 'data-region-field hidden')


@skipUnless(os.environ.get('GITSN_RUN_BROWSER_TESTS') == '1', 'Enable Chromium verification on PostgreSQL.')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CustomerLocationBrowser(StaticLiveServerTestCase):
    def setUp(self):
        user = get_user_model().objects.create_user('loc-browser', password='LocalLocBrowser!52')
        UserAccessProfile.objects.create(user=user, audience='employee')
        user.user_permissions.add(Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery'))

    def test_name_fills_location_manual_choice_kept_and_hidden_for_other_categories(self):
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1280, 'height': 900})
                page.goto(self.live_server_url + '/login/')
                page.get_by_label('아이디', exact=False).fill('loc-browser')
                page.get_by_label('비밀번호', exact=False).fill('LocalLocBrowser!52')
                page.get_by_role('button', name='로그인', exact=True).click()
                page.wait_for_url('**/planning/')
                page.goto(self.live_server_url + reverse('planning-customer-new'))
                box = page.locator('[data-location-fields]')
                hint = page.locator('[data-location-hint]')
                expect(box).to_be_hidden()
                page.locator('[name="category"]').select_option('local')
                expect(box).to_be_visible()
                page.locator('[name="official_name"]').fill('천안시')
                expect(page.locator('[name="location_sido"]')).to_have_value('44')
                expect(page.locator('[name="location_unit"]')).to_have_value(CHEONAN)
                expect(page.locator('[name="institution_type"][value="admin"]')).to_be_checked()
                expect(page.locator('[name="region"]')).to_have_value('chungcheong')
                expect(hint).to_contain_text('충남 천안시')
                # 같은 이름이 여러 곳이면 비우고 후보를 알려준다(제안으로 맞춘 지역도 되돌린다)
                page.locator('[name="official_name"]').fill('중구')
                expect(hint).to_contain_text('선택 필요')
                expect(page.locator('[name="location_sido"]')).to_have_value('')
                expect(page.locator('[name="region"]')).to_have_value('')
                # 직접 고르면 그 시·도의 시군구만 보이고, 지역이 따라가고, 명칭이 바뀌어도 덮어쓰지 않는다
                page.locator('[name="location_sido"]').select_option('41')
                self.assertEqual(page.locator('[name="location_unit"] option').count(), len([u for u in aa.units_in('41') if not aa.UNIT_BY_CODE[u][2]]) + 1)
                expect(page.locator('[name="region"]')).to_have_value('capital')
                page.locator('[name="official_name"]').fill('천안시')
                expect(hint).to_contain_text('명칭 기준 제안')
                expect(page.locator('[name="location_sido"]')).to_have_value('41')
                hint.get_by_role('button', name='적용').click()
                expect(page.locator('[name="location_sido"]')).to_have_value('44')
                # 다른 분류에서는 숨는다
                page.locator('[name="category"]').select_option('public')
                expect(box).to_be_hidden()
                expect(page.locator('[data-region-field]')).to_be_hidden()   # 지역도 지자체·의회에서만(2026-10-22 형우)
                page.locator('[name="category"]').select_option('local')
                expect(page.locator('[data-region-field]')).to_be_visible()
                page.get_by_role('button', name='고객사 등록', exact=True).click()
                page.wait_for_url('**/planning/customers/*/')
                expect(page.get_by_test_id('customer-location')).to_have_text('소재지 충남 천안시 · 행정기관')
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
            finally:
                browser.close()
