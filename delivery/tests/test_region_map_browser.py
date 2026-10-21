"""지역 현황 지도 브라우저 검사(6a~, 리뷰 반영). 실제 고객 데이터와 분리된 검사 DB를 쓴다."""
import os
from datetime import date
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import sync_playwright, expect

from delivery.models import Category, Contract, ContractProduct, Customer, Organization, Product, Region, UserAccessProfile
from delivery.services.region_map import region_map_payload

PASSWORD = 'LocalBrowserExample!77'
# 보이는 버튼 중 44px보다 작은 것(높이나 너비)
SMALL_BUTTONS = """() => [...document.querySelectorAll('[data-rmap] button')]
    .filter(b => b.offsetParent !== null)
    .map(b => { const r = b.getBoundingClientRect();
                return [b.textContent.trim() || b.getAttribute('aria-label'), Math.round(r.width), Math.round(r.height)]; })
    .filter(([, w, h]) => w < 44 || h < 44)"""
# 면 안쪽에서 실제로 그 면이 잡히는 화면 좌표(테두리 상자 가운데는 이웃 면일 수 있다)
POINT_INSIDE = """sel => { const el = document.querySelector(sel); const r = el.getBoundingClientRect();
    for (let i = 1; i < 20; i++) for (let j = 1; j < 20; j++) {
      const x = r.x + r.width * i / 20, y = r.y + r.height * j / 20;
      if (document.elementFromPoint(x, y) === el) return [x, y]; }
    return null; }"""


@skipUnless(os.environ.get('GITSN_RUN_BROWSER_TESTS') == '1', 'Enable Chromium verification on PostgreSQL.')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RegionMapBrowserScenarios(StaticLiveServerTestCase):
    def setUp(self):
        u = get_user_model().objects.create_user('rm-browser', password=PASSWORD)
        UserAccessProfile.objects.create(user=u, audience='employee')
        m = get_user_model().objects.create_user('rm-manager', password=PASSWORD)
        UserAccessProfile.objects.create(user=m, audience='employee')
        m.user_permissions.add(Permission.objects.get(codename='manage_delivery', content_type__app_label='delivery'))
        s = Product.objects.create(code='rmb-s', name='Alpha-S', marker='S')
        c = Product.objects.create(code='rmb-c', name='Alpha-C', marker='C')
        for name, cat, loc, kind, product in [('천안시', Category.LOCAL, '44130', 'admin', s),
                                              ('아산시', Category.LOCAL, '44200', 'admin', c),
                                              ('천안시의회', Category.COUNCIL, '44130', 'admin', s),
                                              ('충청남도', Category.LOCAL, '44', 'admin', s),
                                              ('전남광주통합특별시 광주청사', Category.LOCAL, '12', 'admin', s),
                                              ('전남광주통합특별시 무안청사', Category.LOCAL, '12', 'admin', s),
                                              ('공주 어떤 시설', Category.LOCAL, '44150', 'facility', c),
                                              ('충청남도 산림자원연구소', Category.LOCAL, '44', 'facility', c),
                                              ('소재지 없는 군청', Category.LOCAL, '', '', s)]:
            cu = Customer.objects.create(organization=Organization.objects.create(official_name=name), category=cat,
                                         region=Region.CHUNGCHEONG, partner_public=True, location_code=loc, institution_type=kind)
            k = Contract.objects.create(customer=cu, contracting_party=cu.organization, is_active=True, contract_date=date(2021, 1, 1))
            ContractProduct.objects.create(contract=k, product=product, quantity=1)

    def open_map(self, page, username='rm-browser'):
        page.goto(self.live_server_url + '/login/')
        page.get_by_label('아이디', exact=False).fill(username)
        page.get_by_label('비밀번호', exact=False).fill(PASSWORD)
        page.get_by_role('button', name='로그인', exact=True).click()
        page.wait_for_url(lambda url: '/login/' not in url)  # 관리자는 기획팀 첫 화면으로 간다
        with page.expect_response(lambda r: 'delivery/map/korea-lite.json' in r.url) as resp:
            page.goto(self.live_server_url + '/performance/map/')
        self.assertEqual(resp.value.status, 200)
        expect(page.locator('[data-rmap]')).to_have_attribute('data-ready', '1')

    def painted(self, page):
        return set(page.eval_on_selector_all('.rmap-unit.is-in', 'els => els.map(e => e.dataset.code)'))

    def focused(self, page, js):
        return page.evaluate('() => { const a = document.activeElement; return ' + js + '; }')

    @staticmethod
    def click_unit(page, selector):
        """SVG 면의 테두리 상자 가운데가 이웃 면일 수 있으므로, 그 요소에 직접 클릭 이벤트를 보낸다."""
        page.eval_on_selector(selector, """el => { const r = el.getBoundingClientRect();
            el.dispatchEvent(new MouseEvent('click', {bubbles: true, clientX: r.x + r.width / 2, clientY: r.y + r.height / 2})); }""")

    @staticmethod
    def hover(page, selector):
        page.eval_on_selector(selector, """el => { const r = el.getBoundingClientRect();
            el.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, pointerType: 'mouse', clientX: r.x + r.width / 2, clientY: r.y + r.height / 2})); }""")

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
                page.get_by_label('비밀번호', exact=False).fill(PASSWORD)
                page.get_by_role('button', name='로그인', exact=True).click()
                page.wait_for_url('**/performance/')
                page.goto(self.live_server_url + '/performance/map/')
                expect(page.locator('[data-rmap-error]')).to_be_visible()
            finally:
                browser.close()

    def test_four_combinations_match_the_service_in_map_and_panel(self):
        payload = region_map_payload()  # 브라우저 전에 계산
        labels = {f['key']: f['label'] for f in payload['families']}
        labels.update({t['key']: t['label'] for t in payload['targets']})
        sido_order = [s['code'] for s in payload['sido']]
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                self.open_map(page)
                # 전환 버튼은 한 번만 만들고 눌린 상태만 바꾼다(리뷰 18)
                page.evaluate("() => { window.__rmapBtn = document.querySelector('[data-rmap-switch=\"family\"] button[data-value=\"camera\"]'); }")
                for family in ('eavesdrop', 'camera'):
                    for target in ('local', 'council'):
                        page.locator(f'[data-rmap-switch="family"] button[data-value="{family}"]').click()
                        page.locator(f'[data-rmap-switch="target"] button[data-value="{target}"]').click()
                        expect(page.locator('[data-rmap]')).to_have_attribute('data-combo', f'{family}:{target}')
                        combo = payload['combos'][f'{family}:{target}']
                        expected = {c for c, s in combo['units'].items() if s['state'] == 'in'}
                        self.assertEqual(self.painted(page), expected, f'{family}:{target}')
                        expect(page.locator('[data-rmap-national] strong')).to_have_text(str(combo['national']['adopted']))
                        rows = page.eval_on_selector_all('.rmap-sido-row', 'els => els.map(e => [e.dataset.sido, e.querySelector(".rmap-sido-count").textContent])')
                        self.assertEqual([r[0] for r in rows], sido_order)  # 행정코드 순(순위 아님)
                        self.assertEqual([r[1] for r in rows], [f"{s['adopted']} / {s['total']}" for s in combo['sido']])
                        pressed = page.eval_on_selector_all('[aria-pressed="true"]', 'els => els.map(e => e.textContent)')
                        self.assertEqual(sorted(pressed), sorted([labels[family], labels[target]]))
                self.assertTrue(page.evaluate('() => window.__rmapBtn.isConnected'))
                self.assertEqual(page.locator('[data-rmap-switch] button').count(), 4)
            finally:
                browser.close()

    def test_sido_zoom_lists_and_back(self):
        payload = region_map_payload()  # 브라우저 전에 계산
        names = {code: u['name'] for code, u in payload['units'].items()}
        def sido(combo_key, code):
            return [x for x in payload['combos'][combo_key]['sido'] if x['code'] == code][0]
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                self.open_map(page)
                with page.expect_response(lambda r: 'delivery/map/sido/44.json' in r.url) as resp:
                    page.locator('.rmap-sido-row[data-sido="44"]').click()
                self.assertEqual(resp.value.status, 200)
                root = page.locator('[data-rmap]')
                expect(root).to_have_attribute('data-sido', '44')
                expect(page.locator('[data-rmap-sido-title]')).to_have_text('충청남도')
                # 포커스는 '← 전국'으로 옮겨 간다(리뷰 18)
                self.assertTrue(self.focused(page, "a.hasAttribute('data-rmap-back')"))
                s = sido('eavesdrop:local', '44')
                expect(page.locator('[data-rmap-national] strong')).to_have_text(str(s['adopted']))
                self.assertEqual(page.eval_on_selector_all('[data-rmap-missing] li', 'els => els.map(e => e.textContent)'),
                                 [names[c] for c in s['missing']])
                self.assertEqual(page.eval_on_selector_all('[data-rmap-adopted] .rmap-org-name', 'els => els.map(e => e.textContent)'), ['천안시'])
                # '도입한 곳' 숫자는 목록 줄 수(기관 수)와 같다(리뷰 25)
                expect(page.locator('.rmap-section', has_text='도입한 곳').locator('h2')).to_contain_text('1곳')
                expect(page.locator('[data-rmap-wide]')).to_contain_text('충청남도')
                # 다른 시·도 면은 흐리게, 고른 시·도 테두리는 진하게
                self.assertEqual(page.locator('.rmap-unit.is-dim[data-sido="44"]').count(), 0)
                self.assertGreater(page.locator('.rmap-unit.is-dim').count(), 200)
                expect(page.locator('.rmap-sido.is-selected')).to_have_attribute('data-code', '44')
                # 전환을 바꿔도 시·도 유지
                page.locator('[data-rmap-switch="family"] button[data-value="camera"]').click()
                expect(root).to_have_attribute('data-combo', 'camera:local')
                expect(root).to_have_attribute('data-sido', '44')
                s = sido('camera:local', '44')
                self.assertEqual(page.eval_on_selector_all('[data-rmap-missing] li', 'els => els.map(e => e.textContent)'),
                                 [names[c] for c in s['missing']])
                # 의회를 볼 때는 빠진 곳 이름에 '의회'를 붙인다(리뷰 26)
                page.locator('[data-rmap-switch="family"] button[data-value="eavesdrop"]').click()
                page.locator('[data-rmap-switch="target"] button[data-value="council"]').click()
                s = sido('eavesdrop:council', '44')
                self.assertEqual(page.eval_on_selector_all('[data-rmap-missing] li', 'els => els.map(e => e.textContent)'),
                                 [names[c] + '의회' for c in s['missing']])
                expect(page.locator('.rmap-section h2', has_text='광역의회')).to_have_count(1)
                page.locator('[data-rmap-switch="target"] button[data-value="local"]').click()
                # ← 전국: 포커스는 방금 보던 시·도 줄로 돌아온다
                page.locator('[data-rmap-back]').click()
                expect(root).to_have_attribute('data-sido', '')
                expect(page.locator('.rmap-sido-row')).to_have_count(16)
                self.assertEqual(self.focused(page, 'a.dataset.sido'), '44')
                # 전남광주 광역 줄은 여러 기관을 나열하고, Esc로 전국 복귀
                page.locator('.rmap-sido-row[data-sido="12"]').click()
                expect(page.locator('[data-rmap-wide] [data-org]')).to_have_count(2)
                # 흐리게 한 면도 도입 색은 그대로 둔다(리뷰 10)
                self.assertEqual(page.eval_on_selector('.rmap-unit[data-code="44130"]', 'e => [...e.classList].sort()'),
                                 ['is-dim', 'is-in', 'rmap-unit'])
                page.keyboard.press('Escape')
                expect(root).to_have_attribute('data-sido', '')
                # 지도 면을 눌러도 그 시·도로 간다
                page.locator('.rmap-unit[data-code="44130"]').click(force=True)
                expect(root).to_have_attribute('data-sido', '44')
            finally:
                browser.close()

    def test_tooltip_card_and_facility_marks(self):
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                self.open_map(page)
                root = page.locator('[data-rmap]')
                tip = page.locator('[data-rmap-tip]')
                card = page.locator('[data-rmap-card]')
                # 마우스를 올리면 이름과 도입 여부
                self.hover(page, '.rmap-unit[data-code="44130"]')
                expect(tip).to_be_visible()
                expect(tip).to_contain_text('천안시')
                expect(tip).to_contain_text('도입')
                # 시·도를 고른 뒤 도입 면을 누르면 카드: 정보 네 가지(심볼·이름·제품·연도) + 제품군 이름
                page.locator('.rmap-sido-row[data-sido="44"]').click()
                expect(root).to_have_attribute('data-sido', '44')
                self.click_unit(page, '.rmap-unit[data-code="44130"]')
                expect(card).to_be_visible()
                fields = page.eval_on_selector_all('[data-rmap-card] [data-field]', 'els => els.map(e => [e.dataset.field, e.textContent])')
                self.assertEqual(fields, [['name', '천안시'], ['family', '도청 보안'], ['products', 'Alpha-S'], ['year', '2021']])
                expect(page.locator('[data-rmap-card] .rmap-symbol')).to_have_text('천')  # 심볼이 없으면 글자 타일
                text = card.inner_text()
                for unexpected in ('대', '수량', '금액', '연락처'):
                    self.assertNotIn(unexpected, text.replace('도입 연도', '').replace('도청', ''))
                # Esc는 카드만 닫고 시·도는 유지
                page.keyboard.press('Escape')
                expect(card).to_be_hidden()
                expect(root).to_have_attribute('data-sido', '44')
                # 미도입 면은 이름과 '미도입'만
                self.click_unit(page, '.rmap-unit[data-code="44210"]')
                fields = page.eval_on_selector_all('[data-rmap-card] [data-field]', 'els => els.map(e => [e.dataset.field, e.textContent])')
                self.assertEqual([f[0] for f in fields], ['name', 'status'])
                expect(page.locator('[data-rmap-card] [data-field="status"]')).to_have_text('미도입')
                page.keyboard.press('Escape')
                # 목록에서도 카드를 연다. 닫으면 누른 칸으로 포커스가 돌아온다(리뷰 19 일부)
                page.locator('[data-rmap-missing] li[data-unit="44210"] button').click()
                expect(card).to_be_visible()
                expect(page.locator('[data-rmap-card] [data-field="status"]')).to_have_text('미도입')
                page.keyboard.press('Escape')
                expect(card).to_be_hidden()
                self.assertEqual(self.focused(page, "a.closest('li') && a.closest('li').dataset.unit"), '44210')
                page.locator('[data-rmap-adopted] button.rmap-org').click()
                expect(page.locator('[data-rmap-card] [data-field="name"]')).to_have_text('천안시')
                page.keyboard.press('Escape')
                # 시설 표시는 제품군을 따라간다
                expect(page.locator('.rmap-fac')).to_have_count(0)
                expect(page.locator('[data-rmap-legend-fac]')).to_be_hidden()
                page.locator('[data-rmap-switch="family"] button[data-value="camera"]').click()
                expect(page.locator('.rmap-fac')).to_have_count(1)
                expect(page.locator('.rmap-fac')).to_have_attribute('data-code', '44150')
                expect(page.locator('[data-rmap-legend-fac]')).to_be_visible()
                expect(page.locator('[data-rmap-missing] li[data-unit="44150"] [data-fac]')).to_have_count(1)
                expect(page.locator('[data-rmap-wide] button[data-fac]')).to_contain_text('충청남도 산림자원연구소')
                # 시설 표시에 마우스를 올리면 시설 이름(리뷰 11)
                self.hover(page, '.rmap-fac[data-code="44150"]')
                expect(tip).to_contain_text('공주 어떤 시설')
                # 시설 표시를 누르면 카드에 시설·공기업 칸
                self.click_unit(page, '.rmap-fac[data-code="44150"]')
                expect(page.locator('[data-rmap-card-fac]')).to_contain_text('공주 어떤 시설')
                expect(page.locator('[data-rmap-card] [data-field="status"]')).to_have_text('미도입')
                page.keyboard.press('Escape')
                # 광역 줄의 시설도 눌러서 카드로 본다(리뷰 11)
                page.locator('[data-rmap-wide] button[data-fac]').click()
                expect(page.locator('[data-rmap-card] [data-field="name"]')).to_have_text('충청남도 산림자원연구소')
                page.keyboard.press('Escape')
                # 전국으로 돌아가 축소해도 시설 표시는 화면에서 반지름 7px 이상(리뷰 23)
                page.keyboard.press('Escape')
                expect(root).to_have_attribute('data-sido', '')
                expect(root).to_have_attribute('data-zoom', 'done')
                self.assertGreaterEqual(page.locator('.rmap-fac').bounding_box()['width'], 13.5)
            finally:
                browser.close()

    def test_desktop_fits_one_screen(self):
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                for width, height in ((1280, 800), (1440, 900), (1920, 1080)):
                    page = browser.new_page(viewport={'width': width, 'height': height})
                    self.open_map(page)
                    over = page.evaluate('document.scrollingElement.scrollHeight - innerHeight')
                    self.assertLessEqual(over, 1, f'{width}x{height} 세로 스크롤')
                    # 머리띠(제목·전환·범례)가 지도 위 여백 안에 들어온다(리뷰 4)
                    bar = page.locator('[data-rmap-bar]').bounding_box()
                    svg = page.locator('[data-rmap-canvas] svg').bounding_box()
                    self.assertLessEqual(bar['y'] + bar['height'], svg['y'] + 1)
                    page.close()
            finally:
                browser.close()

    def test_small_screens_sheet_tap_card_and_targets(self):
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                # (폭, 높이, 터치, 아래 시트)
                for width, height, touch, sheet in ((390, 844, True, True), (768, 1024, True, True),
                                                    (1024, 1366, True, True), (1024, 768, True, False),
                                                    (1280, 800, False, False)):
                    page = browser.new_page(viewport={'width': width, 'height': height}, has_touch=touch)
                    self.open_map(page)
                    where = f'{width}x{height}'
                    overflow = page.evaluate('document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth')
                    self.assertLessEqual(overflow, 0, f'{where} 가로 스크롤')
                    if not sheet:
                        expect(page.locator('[data-rmap-sheet-toggle]')).to_be_hidden()
                        if touch:  # 가로 태블릿: 데스크톱 배치지만 누르는 영역은 44px 이상(리뷰 6)
                            self.assertTrue(page.evaluate("matchMedia('(pointer: coarse)').matches"), where)
                            self.assertEqual(page.evaluate(SMALL_BUTTONS), [], f'{where} 44px 미만 버튼')
                            page.locator('.rmap-sido-row[data-sido="44"]').tap()
                            self.assertEqual(page.evaluate(SMALL_BUTTONS), [], f'{where} 시·도 44px 미만 버튼')
                        page.close()
                        continue
                    root = page.locator('[data-rmap]')
                    toggle = page.locator('[data-rmap-sheet-toggle]')
                    # 아래 시트: 처음엔 접힘(요약만), 손잡이로 펼치고 접기
                    expect(root).to_have_attribute('data-sheet', 'closed')
                    toggle.tap()
                    expect(root).to_have_attribute('data-sheet', 'open')
                    toggle.tap()
                    expect(root).to_have_attribute('data-sheet', 'closed')
                    toggle.tap()
                    expect(root).to_have_attribute('data-sheet', 'open')
                    page.locator('.rmap-sido-row[data-sido="44"]').tap()
                    expect(root).to_have_attribute('data-sido', '44')
                    # 시·도를 고르면 시트를 접어 확대한 지도를 가리지 않는다(리뷰 2)
                    expect(root).to_have_attribute('data-sheet', 'closed')
                    # 접힌 시트에서도 시·도 이름과 요약 숫자가 잘리지 않는다(리뷰 1)
                    for sel in ('[data-rmap-sido-title]', '[data-rmap-national]'):
                        box = page.locator(sel).bounding_box()
                        self.assertIsNotNone(box, f'{where} {sel}')
                        self.assertLessEqual(box['y'] + box['height'], height, f'{where} {sel}')
                    # 실제 손가락 탭으로 면을 누르면 카드(마우스 말풍선 없이 같은 정보), 화면 안에 들어온다
                    expect(root).to_have_attribute('data-zoom', 'done')  # 확대가 끝난 뒤에 누른다
                    xy = page.evaluate(POINT_INSIDE, '.rmap-unit[data-code="44130"]')
                    self.assertIsNotNone(xy, f'{where} 천안시 면이 화면에 보이지 않음')
                    page.touchscreen.tap(xy[0], xy[1])
                    card = page.locator('[data-rmap-card]')
                    expect(card).to_be_visible()
                    expect(page.locator('[data-rmap-card] [data-field="name"]')).to_have_text('천안시')
                    box = card.bounding_box()
                    self.assertGreaterEqual(box['x'], 0)
                    self.assertLessEqual(box['x'] + box['width'], width)
                    self.assertLessEqual(box['y'] + box['height'], height)
                    expect(page.locator('[data-rmap-tip]')).to_be_hidden()
                    self.assertEqual(page.evaluate(SMALL_BUTTONS), [], f'{where} 44px 미만 버튼(카드)')
                    page.locator('[data-rmap-card-close]').tap()
                    expect(card).to_be_hidden()
                    # 바닥글이 접힌 시트 뒤에 가려지지 않는다(리뷰 16)
                    page.evaluate('window.scrollTo(0, document.scrollingElement.scrollHeight)')
                    footer = page.locator('footer').bounding_box()
                    sheet_top = page.locator('[data-rmap-panel]').bounding_box()['y']
                    self.assertLessEqual(footer['y'] + footer['height'], sheet_top + 1, f'{where} 바닥글 가림')
                    # 펼친 시트의 칸들도 44px 이상
                    toggle.tap()
                    expect(root).to_have_attribute('data-sheet', 'open')
                    expect(page.locator('[data-rmap-missing]')).to_be_visible()
                    self.assertEqual(page.evaluate(SMALL_BUTTONS), [], f'{where} 44px 미만 버튼(시트)')
                    page.close()
            finally:
                browser.close()

    def test_empty_states_and_unassigned_notice(self):
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                self.open_map(page)
                # 일반 직원(영업 현장)에게는 미지정 안내를 보이지 않는다(리뷰 9)
                expect(page.locator('[data-rmap-unassigned]')).to_have_count(0)
                # 도입 0곳인 시·도: 빠진 곳 = 전체, '아직 도입한 곳이 없습니다'
                page.locator('.rmap-sido-row[data-sido="26"]').click()
                expect(page.locator('[data-rmap-national] strong')).to_have_text('0')
                expect(page.locator('[data-rmap-missing] li')).to_have_count(16)
                expect(page.locator('.rmap-section', has_text='도입한 곳')).to_contain_text('아직 도입한 곳이 없습니다')
                expect(page.locator('[data-rmap-wide]')).to_contain_text('미도입')
                # 상단 메뉴의 '지역 현황'은 지금 화면 표시
                expect(page.locator('nav a[aria-current="page"]')).to_have_text('지역 현황')
                page.close()
                # 기획팀(관리자)에게는 소재지가 빈 기관을 따로 알린다
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                self.open_map(page, 'rm-manager')
                notice = page.locator('[data-rmap-unassigned]')
                expect(notice).to_be_visible()
                expect(notice).to_contain_text('소재지 없는 군청')
                expect(notice).to_contain_text('1곳')
            finally:
                browser.close()
