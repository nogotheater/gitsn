"""Full audience browser flows, isolated from real customer/account records."""
import os
import re
from tempfile import TemporaryDirectory
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import sync_playwright, expect
from delivery.models import Organization, Customer, Contract, ContractProduct, Product, UserAccessProfile


@skipUnless(os.environ.get('GITSN_RUN_BROWSER_TESTS') == '1', 'Enable Chromium verification on PostgreSQL.')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PortalBrowserScenarios(StaticLiveServerTestCase):
    def setUp(self):
        for role in ['manager', 'employee', 'partner']:
            user = get_user_model().objects.create_user('browser-' + role, password='LocalBrowserExample!77')
            UserAccessProfile.objects.create(user=user, audience='partner' if role == 'partner' else 'employee')
            if role == 'manager':
                user.user_permissions.add(Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery'))
        self.c = Product.objects.create(code='browser-portal-c', name='브라우저 가상 C', marker='C')
        self.i = Product.objects.create(code='browser-portal-i', name='브라우저 가상 I', marker='I')
        self.s = Product.objects.create(code='browser-portal-s', name='브라우저 가상 S', marker='S')
        for name, public, products in [('브라우저 공개 기관', True, [self.c, self.i, self.s]), ('BROWSER_PRIVATE_SENTINEL', False, [self.c, self.i]), ('브라우저 단일 제품 기관', True, [self.c])]:
            customer = Customer.objects.create(organization=Organization.objects.create(official_name=name), category='public', partner_public=public)
            contract = Contract.objects.create(customer=customer, contracting_party=customer.organization, is_active=True)
            for product in products:
                ContractProduct.objects.create(contract=contract, product=product, quantity=1)

    def login(self, page, username, password='LocalBrowserExample!77'):
        page.goto(self.live_server_url + '/login/')
        page.get_by_label('아이디', exact=False).fill(username)
        page.get_by_label('비밀번호', exact=False).fill(password)
        page.get_by_role('button', name='로그인', exact=True).click()

    @staticmethod
    def product_chip(page, product):
        return page.locator('#product-panel .product-chip', has_text=product.name)

    def test_employee_partner_filters_mobile_logout_and_direct_detail_denial(self):
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1280, 'height': 900})
                # An old unversioned stylesheet must not be used by the new page.
                page.route(re.compile(r'.*/static/delivery/portal\.css$'), lambda route: route.fulfill(
                    status=200, content_type='text/css', body='/* simulated stale unversioned stylesheet */'))
                self.login(page, 'browser-employee')
                page.wait_for_url('**/performance/')
                self.assertIn('?v=', page.locator('link[href*="delivery/portal.css"]').get_attribute('href'))
                expect(page.locator('.mobile-bar')).to_be_hidden()
                expect(page.get_by_test_id('total-count')).to_have_text('3')
                # Desktop product chips apply at once and the panel stays open across the reload.
                page.locator('[data-product-panel-toggle]').click()
                expect(page.locator('#product-panel')).to_be_visible()
                self.product_chip(page, self.c).click()
                page.wait_for_url('**/*products=' + str(self.c.pk) + '*')
                expect(page.locator('#product-panel')).to_be_visible()
                self.product_chip(page, self.i).click()
                page.wait_for_url('**/*products=' + str(self.i.pk) + '*')
                self.assertIn(str(self.c.pk), page.url)
                expect(page.get_by_test_id('total-count')).to_have_text('3')
                expect(page.locator('.performance-grid .customer-card')).to_have_count(3)
                expect(page.locator('.performance-grid .product-mark.is-subdued')).to_have_count(1)
                expect(page.locator('[data-product-panel-toggle] .filter-badge')).to_have_text('2')
                page.get_by_role('link', name='브라우저 공개 기관', exact=False).first.click()
                page.wait_for_url('**/performance/customers/*/')
                detail = page.url
                self.assertNotIn('메일 출처', page.content())
                page.get_by_role('button', name='로그아웃', exact=True).click()
                self.login(page, 'browser-partner')
                page.wait_for_url('**/performance/')
                expect(page.get_by_test_id('total-count')).to_have_text('3')
                expect(page.get_by_test_id('category-private-count')).to_have_text('비공개 1곳 포함')
                self.assertNotIn('BROWSER_PRIVATE_SENTINEL', page.content())
                self.assertEqual(page.locator('.performance-grid a.customer-card').count(), 0)
                self.assertEqual(page.get_by_role('link', name='계정 관리', exact=True).count(), 0)
                page.set_viewport_size({'width': 375, 'height': 812})
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
                self.assertEqual(page.locator('.performance-grid').first.evaluate('(el) => getComputedStyle(el).gridTemplateColumns.split(" ").length'), 1)
                page.goto(detail)
                expect(page.get_by_role('heading', name='접근 권한이 없습니다')).to_be_visible()
                self.assertNotIn('브라우저 공개 기관', page.content())
            finally:
                browser.close()

    def test_manager_creates_partner_and_resets_password_through_screens(self):
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 375, 'height': 812})
                self.login(page, 'browser-manager')
                page.wait_for_url('**/planning/')
                page.get_by_role('link', name='계정 관리', exact=True).click()
                page.get_by_role('link', name='＋ 계정 만들기', exact=True).click()
                page.get_by_label('로그인 아이디', exact=False).fill('browser-created-partner')
                page.get_by_label('이용 권한', exact=False).select_option('partner')
                page.locator('[name="password1"]').fill('SampleKey!82River')
                page.locator('[name="password2"]').fill('SampleKey!82River')
                page.get_by_role('button', name='계정 만들기', exact=True).click()
                expect(page.locator('.error-text:visible, .errorlist:visible')).to_have_count(0)
                page.wait_for_url(re.compile(r'/planning/accounts/\d+/$'))
                page.get_by_role('link', name='비밀번호 재설정', exact=True).click()
                page.locator('[name="new_password1"]').fill('MountainKey!93Lake')
                page.locator('[name="new_password2"]').fill('MountainKey!93Lake')
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
                page.get_by_role('button', name='새 비밀번호로 변경', exact=True).click()
                page.wait_for_url('**/planning/accounts/')
                page.get_by_role('button', name='로그아웃', exact=True).click()
                self.login(page, 'browser-created-partner', 'MountainKey!93Lake')
                page.wait_for_url('**/performance/')
                self.assertNotIn('BROWSER_PRIVATE_SENTINEL', page.content())
            finally:
                browser.close()

    def test_tabs_search_views_and_mobile_sheet_keep_server_state_and_counts(self):
        for index in range(30):
            customer = Customer.objects.create(organization=Organization.objects.create(official_name=f'스크롤 가상 기관 {index:02}'), category='public', partner_public=True)
            contract = Contract.objects.create(customer=customer, contracting_party=customer.organization, is_active=True)
            ContractProduct.objects.create(contract=contract, product=self.c, quantity=1)
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1280, 'height': 900})
                self.login(page, 'browser-employee')
                page.wait_for_url('**/performance/')
                tabs = page.locator('.tabs-track')
                page.evaluate('window.scrollTo(0, 700)')
                page.wait_for_function('document.querySelector(".category-tabs").getBoundingClientRect().top <= 1')
                self.assertEqual(page.locator('.category-tabs').evaluate('(el) => getComputedStyle(el).position'), 'sticky')
                print_url = page.get_by_role('link', name='인쇄·PDF 미리보기', exact=True).get_attribute('href')

                # Category tabs toggle and combine; the product filter rides along.
                tabs.get_by_role('link', name='지자체', exact=True).click()
                page.wait_for_url('**/*category=local*')
                expect(page.get_by_test_id('total-count')).to_have_text('0')
                expect(page.get_by_role('link', name='필터 모두 해제', exact=True)).to_be_visible()
                tabs.get_by_role('link', name='공공', exact=True).click()
                page.wait_for_url('**/*category=public*')
                self.assertIn('category=local', page.url)
                expect(page.get_by_test_id('total-count')).to_have_text('33')
                expect(tabs.locator('.is-active')).to_have_count(2)
                expect(page.locator('.category-counts')).to_have_count(0)
                tabs.get_by_role('link', name='지자체', exact=True).click()
                page.wait_for_url(re.compile(r'performance/\?category=public$'))
                tabs.get_by_role('link', name='전체', exact=True).click()
                page.wait_for_url(re.compile(r'performance/$'))
                expect(page.locator('.category-counts')).to_be_visible()
                self.assertEqual(page.get_by_role('link', name='인쇄·PDF 미리보기', exact=True).get_attribute('href'), print_url)

                # Desktop product panel: chips apply immediately, active chips remove with one click.
                page.locator('[data-product-panel-toggle]').click()
                self.product_chip(page, self.i).click()
                page.wait_for_url('**/*products=*')
                expect(page.get_by_test_id('total-count')).to_have_text('2')
                expect(page.locator('#product-panel')).to_be_visible()
                expect(page.locator('.active-filters .active-chip')).to_have_count(1)
                url = page.get_by_role('link', name='인쇄·PDF 미리보기', exact=True).get_attribute('href')
                self.assertIn(str(self.i.pk), url)
                page.locator('.active-filters .active-chip').click()
                page.wait_for_url(re.compile(r'performance/$'))
                expect(page.get_by_test_id('total-count')).to_have_text('33')
                page.keyboard.press('Escape')
                expect(page.locator('#product-panel')).to_be_hidden()

                # Name search narrows the list only; counts and the print link ignore it.
                page.locator('#performance-search').fill('단일')
                page.keyboard.press('Enter')
                page.wait_for_url('**/*q=*')
                expect(page.get_by_test_id('total-count')).to_have_text('33')
                expect(page.locator('.performance-grid .customer-card')).to_have_count(1)
                self.assertNotIn('q=', page.get_by_role('link', name='인쇄·PDF 미리보기', exact=True).get_attribute('href'))
                page.locator('.search-clear').click()
                page.wait_for_url(re.compile(r'performance/$'))

                # Card/list view is a remembered browser preference.
                page.locator('.performance-toolbar [data-view="list"]').click()
                expect(page.locator('[data-view-root]')).to_have_class(re.compile(r'view-list'))
                self.assertEqual(page.locator('.performance-grid').first.evaluate('(el) => getComputedStyle(el).gridTemplateColumns.split(" ").length'), 1)
                page.reload()
                expect(page.locator('[data-view-root]')).to_have_class(re.compile(r'view-list'))
                page.locator('.performance-toolbar [data-view="card"]').click()
                expect(page.locator('[data-view-root]')).to_have_class(re.compile(r'view-card'))

                # Mobile: scrollable tabs with step buttons, bottom bar, and a sheet that applies with one button.
                page.set_viewport_size({'width': 375, 'height': 812})
                page.reload()
                expect(page.locator('.mobile-bar')).to_be_visible()
                expect(page.locator('.toolbar-desktop')).to_be_hidden()
                expect(page.locator('[data-tabs-scroll="1"]')).to_be_visible()
                page.locator('[data-tabs-scroll="1"]').click()
                page.wait_for_function('document.querySelector(".tabs-track").scrollLeft > 0')
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
                bar = page.locator('.mobile-bar')
                self.assertLessEqual(abs(bar.bounding_box()['y'] + bar.bounding_box()['height'] - 812), 1)
                sheet = page.locator('#product-sheet')
                bar.locator('[data-sheet-open]').click()
                expect(sheet).to_be_visible()
                sheet.locator('.product-chip', has_text=self.i.name).click()
                expect(sheet.locator('[name="products"][value="' + str(self.i.pk) + '"]')).to_be_checked()
                sheet.get_by_role('button', name='적용', exact=True).click()
                page.wait_for_url('**/*products=*')
                expect(page.get_by_test_id('total-count')).to_have_text('2')
                expect(bar.locator('.filter-badge')).to_have_text('1')
                bar.locator('[data-sheet-open]').click()
                sheet.locator('.product-chip', has_text=self.c.name).click()
                expect(sheet.locator('[name="products"][value="' + str(self.c.pk) + '"]')).to_be_checked()
                sheet.get_by_role('button', name='닫기', exact=True).click()
                expect(sheet).to_be_hidden()
                self.assertNotIn(str(self.c.pk), page.url)
                bar.locator('[data-sheet-open]').click()
                expect(sheet.locator('[name="products"][value="' + str(self.c.pk) + '"]')).not_to_be_checked()
                sheet.get_by_role('button', name='닫기', exact=True).click()
                page.get_by_role('link', name='모두 해제', exact=True).click()
                page.wait_for_url(re.compile(r'performance/$'))
                expect(page.get_by_test_id('total-count')).to_have_text('33')
                expect(page.locator('.performance-grid .product-mark.is-selected')).to_have_count(0)
            finally:
                browser.close()
