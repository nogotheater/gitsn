"""지역 현황 지도 브라우저 검사(6a~). 실제 고객 데이터와 분리된 검사 DB를 쓴다."""
import os
from datetime import date
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import sync_playwright, expect

from delivery.models import Category, Contract, ContractProduct, Customer, Organization, Product, Region, UserAccessProfile
from delivery.services.region_map import region_map_payload


@skipUnless(os.environ.get('GITSN_RUN_BROWSER_TESTS') == '1', 'Enable Chromium verification on PostgreSQL.')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RegionMapBrowserScenarios(StaticLiveServerTestCase):
    def setUp(self):
        u = get_user_model().objects.create_user('rm-browser', password='LocalBrowserExample!77')
        UserAccessProfile.objects.create(user=u, audience='employee')
        s = Product.objects.create(code='rmb-s', name='Alpha-S', marker='S')
        c = Product.objects.create(code='rmb-c', name='Alpha-C', marker='C')
        for name, cat, loc, kind, product in [('천안시', Category.LOCAL, '44130', 'admin', s),
                                              ('아산시', Category.LOCAL, '44200', 'admin', c),
                                              ('천안시의회', Category.COUNCIL, '44130', 'admin', s)]:
            cu = Customer.objects.create(organization=Organization.objects.create(official_name=name), category=cat,
                                         region=Region.CHUNGCHEONG, partner_public=True, location_code=loc, institution_type=kind)
            k = Contract.objects.create(customer=cu, contracting_party=cu.organization, is_active=True, contract_date=date(2021, 1, 1))
            ContractProduct.objects.create(contract=k, product=product, quantity=1)

    def open_map(self, page):
        page.goto(self.live_server_url + '/login/')
        page.get_by_label('아이디', exact=False).fill('rm-browser')
        page.get_by_label('비밀번호', exact=False).fill('LocalBrowserExample!77')
        page.get_by_role('button', name='로그인', exact=True).click()
        page.wait_for_url('**/performance/')
        with page.expect_response(lambda r: 'delivery/map/korea-lite.json' in r.url) as resp:
            page.goto(self.live_server_url + '/performance/map/')
        self.assertEqual(resp.value.status, 200)
        expect(page.locator('[data-rmap]')).to_have_attribute('data-ready', '1')

    def painted(self, page):
        return set(page.eval_on_selector_all('.rmap-unit.is-in', 'els => els.map(e => e.dataset.code)'))

    def test_map_draws_229_units_and_paints_from_the_service(self):
        # DB 조회는 브라우저(비동기 루프)를 띄우기 전에 한다
        expected = {code for code, slot in region_map_payload()['combos']['eavesdrop:local']['units'].items()
                    if slot['state'] == 'in'}
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1280, 'height': 900})
                self.open_map(page)
                expect(page.locator('.rmap-unit')).to_have_count(229)
                expect(page.locator('.rmap-sido')).to_have_count(16)
                self.assertEqual(self.painted(page), expected)
                self.assertEqual(expected, {'44130'})
            finally:
                browser.close()

    def test_missing_boundary_file_shows_a_notice(self):
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1280, 'height': 900})
                page.route('**/delivery/map/korea-lite.json*', lambda route: route.fulfill(status=404, body='missing'))
                page.goto(self.live_server_url + '/login/')
                page.get_by_label('아이디', exact=False).fill('rm-browser')
                page.get_by_label('비밀번호', exact=False).fill('LocalBrowserExample!77')
                page.get_by_role('button', name='로그인', exact=True).click()
                page.wait_for_url('**/performance/')
                page.goto(self.live_server_url + '/performance/map/')
                expect(page.locator('[data-rmap-error]')).to_be_visible()
            finally:
                browser.close()
