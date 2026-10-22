"""납품현황 룩(2026-10-21 형우 확정)과 C2 권역별 섹션 검사.

- C2: 지자체·의회는 '지방자치단체(수도권)' 형식 섹션, 순서 수도권→충청권→호남권→영남권→강원권,
  제목 숫자는 고객사 수(권역 합 = 분류 합), 인쇄·PDF도 같은 섹션. 탭·요약 칸은 분류 단위 그대로.
- 룩: 안내 줄 삭제, 폰 제목 '지슨 고객사', 카드 8px, 폰 ☰ 한 줄, 누르는 곳 44px, 인쇄 화면은 그대로.
"""
import os
from tempfile import TemporaryDirectory
from unittest import skipUnless
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import SimpleTestCase, TestCase, override_settings
from playwright.sync_api import sync_playwright, expect
from delivery.models import Customer, Organization, Contract, ContractProduct, Product, UserAccessProfile
from delivery.services.sections import sections


def make_user(name, audience, password='LocalLookExample!61'):
    user = get_user_model().objects.create_user(name, password=password)
    UserAccessProfile.objects.create(user=user, audience=audience)
    return user


def make_customer(name, category, region='', public=True, product=None):
    customer = Customer.objects.create(organization=Organization.objects.create(official_name=name), partner_public=public,
                                       category=category, region=region)
    if product is not None:
        contract = Contract.objects.create(customer=customer, contracting_party=customer.organization, is_active=True)
        ContractProduct.objects.create(contract=contract, product=product, quantity=1)
    return customer


class SectionOrderUnit(SimpleTestCase):
    def test_split_categories_follow_region_order_and_sum_to_category(self):
        counts = {'by_category': {'central': 2, 'local': 5, 'council': 1},
                  'private_by_category': {'local': 1},
                  'by_category_region': {'central:capital': 2, 'local:yeongnam': 1, 'local:capital': 3, 'local:': 1, 'council:gangwon': 1},
                  'private_by_category_region': {'local:capital': 1}}
        out = sections(counts)
        local = [s for s in out if s['code'] == 'local']
        self.assertEqual([s['label'] for s in local], ['지방자치단체(수도권)', '지방자치단체(충청권)', '지방자치단체(호남권)',
                                                    '지방자치단체(영남권)', '지방자치단체(강원권)', '지방자치단체'])
        self.assertEqual([s['count'] for s in local], [3, 0, 0, 1, 0, 1])
        self.assertEqual(sum(s['count'] for s in local), counts['by_category']['local'])
        self.assertEqual(local[0]['private_count'], 1)
        central = [s for s in out if s['code'] == 'central']
        self.assertEqual([(s['label'], s['count'], s['region']) for s in central], [('중앙정부', 2, '')])
        self.assertEqual(len({s['key'] for s in out}), len(out))


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RegionSectionsHttp(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = make_user('look-employee', 'employee')
        cls.partner = make_user('look-partner', 'partner')
        cls.p = Product.objects.create(code='look-p', name='가상 P', marker='P')
        make_customer('가상 중앙 기관', 'central', product=cls.p)
        make_customer('가 강원 가상 군청', 'local', 'gangwon', product=cls.p)
        make_customer('나 수도권 가상 시청', 'local', 'capital', product=cls.p)
        make_customer('다 수도권 가상 구청', 'local', 'capital', public=False, product=cls.p)
        make_customer('라 충청 가상 시청', 'local', 'chungcheong', product=cls.p)
        make_customer('마 호남 가상 의회', 'council', 'honam', product=cls.p)

    def setUp(self):
        self.enterContext(override_settings(MEDIA_ROOT=self.enterContext(TemporaryDirectory())))

    def get(self, user, path='/performance/', query=None):
        self.client.force_login(user)
        return self.client.get(path, query or {})

    def test_list_sections_split_local_and_council_by_region_in_order(self):
        response = self.get(self.employee)
        groups = response.context['list_groups']
        self.assertEqual([(g['label'], g['count']) for g in groups], [
            ('중앙정부', 1), ('지방자치단체(수도권)', 2), ('지방자치단체(충청권)', 1), ('지방자치단체(강원권)', 1),
            ('지방자치단체 의회(호남권)', 1)])
        local_total = response.context['counts']['by_category']['local']
        self.assertEqual(sum(g['count'] for g in groups if g['code'] == 'local'), local_total)
        capital = groups[1]
        self.assertEqual([item['name'] for item in capital['items']], ['나 수도권 가상 시청', '다 수도권 가상 구청'])
        self.assertContains(response, 'id="category-local-capital"')
        # 요약 칸은 분류 단위 그대로.
        self.assertContains(response, '<span>지방자치단체</span><strong>4<small>곳</small></strong>', html=True)

    def test_category_chips_keep_their_own_counts_when_a_category_is_picked(self):
        response = self.get(self.employee, query={'category': 'local'})
        chips = {g['code']: g for g in response.context['groups']}
        self.assertEqual(response.context['counts']['total'], 4)
        self.assertEqual((chips['central']['count'], chips['central']['active']), (1, False))
        self.assertEqual((chips['local']['count'], chips['local']['active']), (4, True))
        self.assertNotIn('category=local', chips['local']['url'])
        self.assertContains(response, 'data-category-chips')
        self.assertContains(response, 'is-dim')
        self.assertNotContains(response, 'category-tabs')

    def test_partner_sees_private_count_on_its_region_section(self):
        groups = self.get(self.partner).context['list_groups']
        capital = next(g for g in groups if g['label'] == '지방자치단체(수도권)')
        self.assertEqual((capital['count'], capital['private_count'], len(capital['items'])), (2, 1, 1))

    def test_blank_region_goes_last_under_plain_category_label(self):
        make_customer('바 지역 미입력 가상 군청', 'local', '', product=self.p)
        labels = [g['label'] for g in self.get(self.employee).context['list_groups'] if g['code'] == 'local']
        self.assertEqual(labels[-1], '지방자치단체')

    def test_region_sections_hold_all_rows_without_pages(self):
        # 2026-10-22 형우: 페이지 없음(기준 변경 이유)
        for index in range(24):
            make_customer(f'수도권 가상 기관 {index:02}', 'local', 'capital', product=self.p)
        groups = self.get(self.employee, query={'category': 'local'}).context['list_groups']
        capital = groups[0]
        self.assertEqual((capital['label'], capital['count'], len(capital['items']), capital['continued']),
                         ('지방자치단체(수도권)', 26, 26, False))

    def test_print_document_uses_the_same_region_sections(self):
        response = self.get(self.employee, '/performance/print/')
        self.assertEqual([g['label'] for g in response.context['groups']], [
            '중앙정부', '지방자치단체(수도권)', '지방자치단체(충청권)', '지방자치단체(강원권)', '지방자치단체 의회(호남권)'])
        self.assertIn({'label': '지방자치단체', 'count': 4}, response.context['category_totals'])

    def test_intro_line_removed_and_short_title_present(self):
        response = self.get(self.employee)
        self.assertNotContains(response, '직원 열람')
        self.assertNotContains(response, '계약 기준 실적 ·')
        self.assertContains(response, '<span class="title-short">지슨 고객사</span>', html=True)
        self.assertNotContains(self.get(self.partner), '파트너사 열람')


@skipUnless(os.environ.get('GITSN_RUN_BROWSER_TESTS') == '1', 'Enable Chromium verification on PostgreSQL.')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PerformanceLookBrowser(StaticLiveServerTestCase):
    def setUp(self):
        make_user('look-browser', 'employee')
        product = Product.objects.create(code='look-browser-p', name='룩 가상 P', marker='P')
        for index in range(12):
            make_customer(f'룩 가상 기관 {index}', 'public', product=product)
        make_customer('룩 수도권 가상 시청', 'local', 'capital', product=product)

    def test_desktop_look_phone_menu_targets_and_print_untouched(self):
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1280, 'height': 900})
                page.goto(self.live_server_url + '/login/')
                page.get_by_label('아이디', exact=False).fill('look-browser')
                page.get_by_label('비밀번호', exact=False).fill('LocalLookExample!61')
                page.get_by_role('button', name='로그인', exact=True).click()
                page.wait_for_url('**/performance/')
                style = lambda selector, prop: page.locator(selector).first.evaluate(f'(el) => getComputedStyle(el).{prop}')
                expect(page.locator('.page-head .intro')).to_have_count(0)
                expect(page.locator('.title-full')).to_be_visible()
                expect(page.locator('.title-short')).to_be_hidden()
                expect(page.locator('.look-menu-btn')).to_be_hidden()
                expect(page.locator('.topbar nav')).to_be_visible()
                self.assertEqual(style('body', 'backgroundColor'), 'rgb(242, 245, 248)')
                self.assertEqual(style('.view-card .performance-grid .customer-card', 'borderRadius'), '8px')
                expect(page.locator('.category-tabs')).to_have_count(0)  # 2026-10-22: 탭 대신 분류 칸
                self.assertNotEqual(style('.performance-summary', 'backdropFilter'), 'none')
                expect(page.get_by_role('heading', name='지방자치단체(수도권)')).to_be_visible()
                # 섹션 접기: 1280px은 한 줄 4개 → 두 줄 8개만. '모두 보기 ▾' ↔ '접기 ▴'(2026-10-22 형우)
                visible = lambda: page.locator('#section-public .customer-card').evaluate_all('cs => cs.filter(c => c.offsetParent).length')
                more = page.locator('#section-public [data-section-more]')
                expect(more).to_have_text('더 보기 ▾')
                self.assertEqual(visible(), 8)
                more.click()   # 두 줄씩 더(12개라 다 보임)
                expect(more).to_have_text('접기 ▴')
                expect(page.locator('#section-public [data-section-fold]')).to_be_visible()
                self.assertEqual(visible(), 12)
                # 섹션 바로가기: 띠의 '목차 ▾' → 분류 줄(지자체·의회는 권역 칩) → 섹션으로 이동
                page.evaluate('window.scrollTo(0, document.documentElement.scrollHeight)')
                toggle = page.locator('[data-band-toggle]')
                expect(toggle).to_be_visible()
                expect(toggle).to_contain_text('목차')
                toggle.click()
                panel = page.locator('[data-band-panel]')
                expect(panel).to_be_visible()
                expect(panel.locator('li')).to_have_count(2)
                expect(panel.locator('.band-region')).to_have_text(['수도권'])
                panel.get_by_role('button', name='공공기관', exact=False).click()
                expect(panel).to_be_hidden()
                page.wait_for_function('Math.abs(document.getElementById("section-public").getBoundingClientRect().top - 72) < 6')
                # 제목 옆 '접기 ▴'로 다시 두 줄
                page.locator('#section-public [data-section-fold]').click()
                expect(more).to_have_text('더 보기 ▾')
                self.assertEqual(visible(), 8)

                # 폰: ☰ 한 줄, 제목 축약, 누르는 곳 44px, 가로 스크롤 없음.
                page.set_viewport_size({'width': 375, 'height': 812})
                page.reload()
                expect(page.locator('.title-short')).to_have_text('지슨 고객사')
                expect(page.locator('.title-full')).to_be_hidden()
                # 폰 리스트(2026-10-22 형우): 전체 보기에서 섹션마다 5줄, 한 줄 배치, ↑ 동그라미
                self.assertTrue(page.locator('[data-view-root]').evaluate("el => el.classList.contains('view-list')"))
                self.assertEqual(visible(), 5)
                expect(more).to_have_text('더 보기 ▾')
                more.click()   # 리스트는 열 줄씩 더(12개라 다 보임)
                self.assertEqual(visible(), 12)
                expect(more).to_have_text('접기 ▴')
                row = page.locator('#section-public .customer-card').first.bounding_box()
                self.assertLess(row['height'], 56)
                expect(page.locator('.section-label .hint')).to_be_hidden()
                self.assertEqual(style('.page-head h1', 'fontSize'), '22px')
                menu = page.locator('.look-menu-btn')
                expect(menu).to_be_visible()
                expect(page.locator('.topbar nav')).to_be_hidden()
                self.assertLessEqual(page.locator('.topbar').bounding_box()['height'], 50)
                menu.click()
                expect(menu).to_have_attribute('aria-expanded', 'true')
                expect(page.locator('.topbar nav')).to_be_visible()
                expect(page.get_by_role('button', name='로그아웃', exact=True)).to_be_visible()
                heights = page.evaluate('''[...document.querySelectorAll('.topbar nav a, .topbar form .button, .look-menu-btn, .mobile-bar > .button, .mobile-bar .view-toggle button, .category-chip')]
                    .filter(el => el.offsetParent).map(el => el.getBoundingClientRect().height)''')
                self.assertTrue(heights and min(heights) >= 44, heights)
                menu.click()
                expect(page.locator('.topbar nav')).to_be_hidden()
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
                page.set_viewport_size({'width': 360, 'height': 740})
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))

                # 인쇄 매체에서는 룩이 적용되지 않는다(바탕색 없음).
                page.emulate_media(media='print')
                self.assertNotEqual(style('body', 'backgroundColor'), 'rgb(242, 245, 248)')
            finally:
                browser.close()
