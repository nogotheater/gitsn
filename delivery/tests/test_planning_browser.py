"""Optional real-browser test on the isolated PostgreSQL test DB."""
import os
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import sync_playwright
from delivery.models import Product, UserAccessProfile


@skipUnless(os.environ.get('GITSN_RUN_BROWSER_TESTS') == '1', 'Enable GITSN_RUN_BROWSER_TESTS=1 for Chromium verification.')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PlanningBrowserScenarios(StaticLiveServerTestCase):
    def test_desktop_registration_mobile_layout_and_logout(self):
        user = get_user_model().objects.create_user('browser-planning', password='BrowserTestOnly!27')
        UserAccessProfile.objects.create(user=user, audience='employee')
        user.user_permissions.add(Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery'))
        c = Product.objects.create(code='browser-c', name='가상 제품 C', marker='C')
        i = Product.objects.create(code='browser-i', name='가상 제품 I', marker='I')
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1280, 'height': 900})
                page.goto(self.live_server_url + '/login/')
                page.get_by_label('아이디').fill('browser-planning')
                page.get_by_label('비밀번호').fill('BrowserTestOnly!27')
                page.get_by_role('button', name='로그인', exact=True).click()
                page.wait_for_url('**/planning/')
                page.get_by_role('link', name='＋ 고객사 등록', exact=True).click()
                page.locator('[name="official_name"]').fill('브라우저 가상 고객사')
                page.locator('[name="category"]').select_option('public')
                page.locator('form[data-presentation-form] button[type="submit"]').click()
                page.wait_for_url('**/planning/customers/*/')
                page.get_by_role('link', name='＋ 계약 추가', exact=True).click()
                page.locator('[name="products-0-product"]').select_option(str(c.pk))
                page.locator('[name="products-0-quantity"]').fill('10')
                page.get_by_role('button', name='＋ 제품 추가', exact=True).click()
                page.locator('[name="products-1-product"]').select_option(str(i.pk))
                page.locator('[name="products-1-quantity"]').fill('5')
                page.get_by_role('button', name='＋ 설치 장소 추가', exact=True).click()
                page.locator('[name="sites-0-new_site_name"]').fill('브라우저 가상 장소')
                page.locator('[name="sites-0-products"][value="' + str(c.pk) + '"]').check()
                page.locator('form[data-contract-form] button[type="submit"]').click()
                page.wait_for_url('**/planning/contracts/*/')
                detail_url = page.url
                self.assertEqual(page.locator('.total strong').inner_text(), '15')
                page.evaluate('document.fonts.ready')
                self.assertTrue(page.evaluate('document.fonts.check(\'16px "Freesentation VF"\')'))
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
                page.set_viewport_size({'width': 375, 'height': 812})
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
                page.get_by_role('link', name='계약 수정', exact=True).click()
                page.wait_for_url('**/edit/')
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
                self.assertEqual(page.locator('[name="products-TOTAL_FORMS"]').input_value(), '2')
                page.get_by_role('button', name='로그아웃', exact=True).click()
                page.wait_for_url('**/login/')
                page.goto(self.live_server_url + '/planning/')
                page.wait_for_url('**/login/**')
                self.assertNotIn('브라우저 가상 고객사', page.content())
                page.get_by_label('아이디').fill('browser-planning')
                page.get_by_label('비밀번호').fill('BrowserTestOnly!27')
                page.get_by_role('button', name='로그인', exact=True).click()
                page.wait_for_url('**/planning/')
                page.goto(detail_url)
                self.assertEqual(page.locator('.total strong').inner_text(), '15')
            finally:
                browser.close()


@skipUnless(os.environ.get('GITSN_RUN_BROWSER_TESTS') == '1', 'Enable GITSN_RUN_BROWSER_TESTS=1 for Chromium verification.')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CustomerPeriodBrowserScenarios(StaticLiveServerTestCase):
    def test_period_buttons_change_the_list_without_reloading_the_page(self):
        # 2026-11-17 형우 '버튼 누를 때 딜레이가 너무 길어' → 누른 버튼은 바로 바뀌고 목록만 바꾼다(뒤로 가기도 된다)
        # 2026-11-18 형우: 등록월 없앰(계약월만), 막대에 마우스를 올리면 고객 분류별 제품, '이전' 연도 메뉴는 가로로
        from datetime import date
        from unittest import mock
        from delivery.models import Contract, ContractProduct, Customer, Organization
        user = get_user_model().objects.create_user('browser-period', password='BrowserTestOnly!27')
        UserAccessProfile.objects.create(user=user, audience='employee')
        user.user_permissions.add(Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery'))
        c = Product.objects.create(code='browser-period-c', name='가상 기간 C', marker='C')
        for name, day in [('기간 시월 기관', date(2026, 10, 1)), ('기간 십일월 기관', date(2026, 11, 5))] + [
                (f'기간 옛 기관 {year}', date(year, 3, 1)) for year in range(2015, 2023)]:
            customer = Customer.objects.create(organization=Organization.objects.create(official_name=name), category='central', partner_public=True)
            contract = Contract.objects.create(customer=customer, contracting_party=customer.organization, is_active=True, contract_date=day)
            ContractProduct.objects.create(contract=contract, product=c, quantity=1)
        with mock.patch('django.utils.timezone.localdate', return_value=date(2026, 11, 17)), sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1280, 'height': 900})
                page.goto(self.live_server_url + '/login/')
                page.get_by_label('아이디').fill('browser-period')
                page.get_by_label('비밀번호').fill('BrowserTestOnly!27')
                page.get_by_role('button', name='로그인', exact=True).click()
                page.wait_for_url('**/planning/')
                page.goto(self.live_server_url + '/planning/?month=all')
                self.assertIn('기간 시월 기관', page.content())
                self.assertEqual(page.get_by_text('등록월', exact=True).count(), 0)
                page.locator('[data-swap="month-2026-10"]').hover()
                tip = page.locator('[data-swap="month-2026-10"] .period-tip')
                self.assertTrue(tip.is_visible())
                self.assertIn('중앙정부', tip.inner_text())
                self.assertIn('1건', tip.inner_text())
                page.evaluate('window.__samePage = 1')
                page.locator('[data-swap="month-2026-11"]').click()
                page.wait_for_selector('.period-result h2:has-text("2026년 11월 계약 · 1곳")')
                self.assertIn('month=2026-11', page.url)
                self.assertEqual(page.evaluate('window.__samePage'), 1)
                self.assertNotIn('기간 시월 기관', page.locator('[data-period-root]').inner_text())
                page.locator('[data-swap="month-2026-10"]').click()
                self.assertEqual(page.locator('[data-swap="month-2026-10"].sel').count(), 1)    # 누르자마자 선택 표시
                page.wait_for_url('**month=2026-10**')                                           # 목록은 받은 뒤 바뀐다
                page.wait_for_selector('[data-period-root]:not([aria-busy])')
                self.assertEqual(page.evaluate('window.__samePage'), 1)
                page.go_back()
                page.wait_for_selector('.period-result h2:has-text("2026년 11월 계약 · 1곳")')
                self.assertEqual(page.evaluate('window.__samePage'), 1)
                page.locator('.period-older summary').click()
                menu = page.locator('.period-older > div')
                links = menu.locator('a').all()
                self.assertGreaterEqual(len(links), 3)
                boxes = [link.bounding_box() for link in links[:3]]
                self.assertEqual(len({round(box['y']) for box in boxes}), 1)                    # 한 줄에 가로로 세 개
                self.assertTrue(all(box['height'] < 50 and box['width'] >= 48 for box in boxes))   # 숫자가 세로로 쪼개지지 않음
                page.mouse.click(10, 10)
                self.assertFalse(menu.is_visible())                                               # 바깥을 누르면 닫힘
            finally:
                browser.close()
