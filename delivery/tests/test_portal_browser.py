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
                # 2026-10-22 형우: 폰 카드형은 한 줄에 두 장(전에는 한 장)
                self.assertEqual(page.locator('.performance-grid').first.evaluate('(el) => getComputedStyle(el).gridTemplateColumns.split(" ").length'), 2)
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
                # 2026-10-22 형우: 분류 탭 줄을 없애고 요약의 분류 칸을 버튼으로 쓴다(기준 변경 이유).
                # 칸은 새로고침 없이 바뀌고, 다시 누르면 빠지며, 칸 숫자는 분류 선택과 상관없이 각자 숫자다.
                expect(page.locator('.category-tabs')).to_have_count(0)
                chips = page.locator('[data-category-chips]')
                chip = lambda code: chips.locator(f'[data-category="{code}"]')
                page.evaluate('window.__live = 1')
                print_url = page.get_by_role('link', name='인쇄·PDF 미리보기', exact=True).get_attribute('href')
                history_length = page.evaluate('history.length')
                # 0곳 칸은 누를 수 없다(2026-10-22 형우). 이 검사 자료에는 지자체가 없다.
                expect(chip('local')).to_have_class(re.compile('is-empty'))
                self.assertEqual(chip('local').evaluate('el => el.tagName'), 'SPAN')
                chip('public').click()
                page.wait_for_url('**/*category=public*')
                expect(page.get_by_test_id('total-count')).to_have_text('33')
                expect(chips.locator('.is-active')).to_have_count(1)
                expect(chip('central')).to_have_class(re.compile('is-empty'))
                expect(chip('public').locator('strong')).to_contain_text('33')
                chip('public').click()
                page.wait_for_url(re.compile(r'performance/$'))
                expect(chips.locator('.is-active')).to_have_count(0)
                self.assertEqual(page.evaluate('window.__live'), 1)
                self.assertEqual(page.evaluate('history.length'), history_length)  # 칩을 눌러도 뒤로 가기 기록은 쌓이지 않는다
                self.assertEqual(page.get_by_role('link', name='인쇄·PDF 미리보기', exact=True).get_attribute('href'), print_url)
                # 0곳이어도 이미 고른 칸은 눌러서 해제할 수 있다
                page.goto(self.live_server_url + '/performance/?category=local')
                expect(page.get_by_test_id('total-count')).to_have_text('0')
                expect(page.get_by_role('link', name='필터 모두 해제', exact=True)).to_be_visible()
                chip('local').click()
                page.wait_for_url(re.compile(r'performance/$'))
                expect(page.get_by_test_id('total-count')).to_have_text('33')
                page.evaluate('window.__live = 1')
                # 띠: 분류 칸이 지나가면 뜨고 지금 보는 섹션을 보여준다. '맨 위로'로 돌아간다.
                band = page.locator('[data-category-band]')
                expect(band).to_be_hidden()
                # 공공기관 33곳: 1280px 4열 → 8개, '더 보기'는 두 줄(8개)씩 → 4번이면 다 보이고 '접기 ▴'
                more = page.locator('#section-public [data-section-more]')
                for expected in (16, 24, 32, 33):
                    expect(more).to_have_text('더 보기 ▾')
                    more.click()
                    self.assertEqual(page.locator('#section-public .customer-card').evaluate_all('cs => cs.filter(c => c.offsetParent).length'), expected)
                expect(more).to_have_text('접기 ▴')
                page.evaluate('window.scrollTo(0, 1200)')
                expect(band).to_be_visible()
                expect(band.locator('.band-value')).to_have_text('공공기관')
                # 떠 있는 파란 알약(🔍 | ↑). PC는 띠 한 줄에 필터·검색·목차(2026-10-22 형우): 🔍는 띠 검색칸으로 커서를 옮긴다.
                # 띠는 바뀔 때 새로 그리지 않는다(깜박임 없음) — 같은 요소인지 표시해 두고 끝까지 확인한다.
                page.evaluate("document.querySelector('[data-category-band]').__same = 1")
                page.locator('[data-float-search]').click()
                band_input = page.locator('[data-band-inline-input]')
                expect(band_input).to_be_focused()
                band_input.fill('단일')
                page.wait_for_url('**/*q=*')
                expect(page.locator('.performance-grid .customer-card')).to_have_count(1)
                expect(page.locator('#performance-search')).to_have_value('단일')
                expect(band).to_be_visible()   # 결과가 짧아져도 치는 동안 띠는 그대로
                band_input.press('Escape')
                page.wait_for_url(re.compile(r'performance/$'))
                expect(band_input).to_have_value('')
                expect(page.locator('.performance-grid .customer-card')).to_have_count(33)
                # 띠 필터(PC): 띠 아래 제품 칩, 고르면 그 자리에서 바뀌고 패널은 열린 채로
                for _ in range(4):
                    more.click()
                expect(more).to_have_text('접기 ▴')
                page.evaluate('window.scrollTo(0, 1200)')
                page.locator('[data-band-filter]').click()
                band_filter = page.locator('[data-band-filter-panel]')
                expect(band_filter).to_be_visible()
                band_filter.locator('.product-chip', has_text=self.i.name).click()
                page.wait_for_url('**/*products=*')
                expect(band_filter).to_be_visible()
                expect(page.locator('[data-band-filter] .filter-badge')).to_have_text('1')
                self.assertEqual(page.evaluate("document.querySelector('[data-category-band]').__same"), 1)
                band_filter.locator('.product-chip', has_text=self.i.name).click()
                page.wait_for_url(re.compile(r'performance/$'))
                page.keyboard.press('Escape')
                expect(band_filter).to_be_hidden()
                self.assertEqual(page.evaluate('window.__live'), 1)
                # 조건이 바뀌면 섹션은 다시 접힌 상태로 그려진다 — 펼쳐서 내려간 뒤 맨 위로를 누른다
                for _ in range(4):
                    more.click()
                page.evaluate('window.scrollTo(0, 1200)')
                to_top = page.locator('[data-to-top]')
                expect(to_top).to_be_visible()
                to_top.click()
                page.wait_for_function('window.scrollY < 2')
                expect(band).to_be_hidden()

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
                self.assertEqual(page.evaluate('window.__live'), 1)  # 제품 칩·조건 해제도 새로고침 없이
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
                expect(page.locator('[data-category-chips]')).to_be_visible()
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
                # 폰 검색(2026-10-22 형우): 🔍를 다시 누르거나 키보드를 내리면 검색창이 닫힌다. 걸러진 결과는 그대로, 지우기는 ×.
                expect(page.locator('.band-inline-search')).to_be_hidden()
                public_more = page.locator('#section-public [data-section-more]')
                while public_more.text_content().strip() == '더 보기 ▾':
                    public_more.click()
                page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                float_search = page.locator('[data-float-search]')
                overlay = page.locator('[data-band-search]')
                float_search.click()
                expect(overlay).to_be_visible()
                float_search.click()
                expect(overlay).to_be_hidden()
                float_search.click()
                overlay.locator('input').fill('스크롤')
                page.wait_for_url('**/*q=*')
                expect(page.locator('.performance-grid .customer-card')).to_have_count(30)
                float_search.click()   # 검색창이 열려 있는 동안 알약은 계속 보인다
                expect(overlay).to_be_hidden()
                self.assertIn('q=', page.url)
                page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                float_search.click()
                expect(overlay.locator('input')).to_have_value('스크롤')
                overlay.locator('input').blur()
                expect(overlay).to_be_hidden()
                page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                float_search.click()
                overlay.locator('[data-band-search-close]').click()
                page.wait_for_url(re.compile(r'performance/$'))
                expect(overlay).to_be_hidden()
                page.evaluate('window.scrollTo(0, 0)')
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
