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
                # 전국 숫자: 광역(충남 1 + 전남광주 두 청사 2) 3 + 기초(천안) 1 = 4 / 244
                expect(page.locator('[data-rmap-national]')).to_have_text('4/ 244')
                expect(page.locator('[data-rmap-part="wide"]')).to_contain_text('3 / 17')
                expect(page.locator('[data-rmap-part="basic"]')).to_contain_text('1 / 227')
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
                        # 전국 = 광역 + 기초, 아래에 두 줄로 나눔(spec v4 7)
                        for part in ('wide', 'basic'):
                            n = combo['national'][part]
                            expect(page.locator(f'[data-rmap-part="{part}"] [data-part-value]')).to_have_text(f"{n['adopted']} / {n['total']}")
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
                # spec v4 6: 제품명 대신 마킹 글자(S). 제품명은 보이지 않는다
                self.assertEqual(fields, [['name', '천안시'], ['family', '도청 보안'], ['marks', 'S'], ['year', '2021']])
                # 20:20: 누른 면은 카드가 열려 있는 동안 진한 색 유지, 닫으면 원래 색
                expect(page.locator('.rmap-unit[data-code="44130"]')).to_have_class('rmap-unit is-in is-picked')
                expect(page.locator('.rmap-unit[data-code="44130"]')).to_have_css('fill', 'rgb(47, 90, 158)')
                self.assertNotIn('Alpha-S', card.inner_text())
                self.assertNotIn('Alpha-S', page.locator('[data-rmap-panel]').inner_text())
                expect(page.locator('[data-rmap-card] .rmap-symbol')).to_have_text('천')  # 심볼이 없으면 글자 타일
                text = card.inner_text()
                for unexpected in ('대', '수량', '금액', '연락처'):
                    self.assertNotIn(unexpected, text.replace('도입 연도', '').replace('도청', ''))
                # Esc는 카드만 닫고 시·도는 유지
                page.keyboard.press('Escape')
                expect(card).to_be_hidden()
                self.assertEqual(page.locator('.rmap-unit.is-picked').count(), 0)
                # 제품군 색: 도청 보안 = 파랑 #4E7CC7 (카드를 닫아 '누른 색'이 풀린 뒤에 본다)
                expect(page.locator('.rmap-unit[data-code="44130"]')).to_have_css('fill', 'rgb(78, 124, 199)')
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
                # 불법촬영 보안 = 코랄 #EA6759 (아산시 C 도입)
                expect(page.locator('.rmap-unit[data-code="44200"]')).to_have_css('fill', 'rgb(234, 103, 89)')
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
                fac_w = page.locator('.rmap-fac').bounding_box()['width']
                self.assertGreaterEqual(fac_w, 13.5)
                self.assertLessEqual(fac_w, 17)  # 18:03: 지도를 화면 전체로 넓힌 뒤 커지던 문제 — 화면에서 늘 같은 크기
            finally:
                browser.close()

    def test_wide_badges_and_status_cards(self):
        # spec v4 1(A+D): 지도 위 광역 배지와 시·도 화면의 광역 상태 카드
        payload = region_map_payload()  # 브라우저 전에 계산
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                self.open_map(page)
                for family, target, word in (('eavesdrop', 'local', '광역'), ('camera', 'local', '광역'),
                                             ('eavesdrop', 'council', '의회'), ('camera', 'council', '의회')):
                    page.locator(f'[data-rmap-switch="family"] button[data-value="{family}"]').click()
                    page.locator(f'[data-rmap-switch="target"] button[data-value="{target}"]').click()
                    rows = payload['combos'][f'{family}:{target}']['sido']
                    expected = {r['code']: ('in' if r['wide_count'] >= r['wide_slots'] else 'part' if r['wide_count'] else 'out')
                                for r in rows}
                    got = dict(page.eval_on_selector_all('.rmap-badge[data-sido]', 'els => els.map(e => [e.dataset.sido, e.dataset.state])'))
                    self.assertEqual(got, expected, f'{family}:{target}')  # 17:17 세종·제주 포함 16개
                    names = page.eval_on_selector_all('.rmap-badge[data-sido]', 'els => els.map(e => e.textContent)')
                    self.assertEqual(all(n.split(' ')[0].endswith('의회') for n in names), word == '의회')
                    overlap = page.evaluate('''() => { const r = [...document.querySelectorAll('.rmap-badge[data-sido]')].map(b => [b.dataset.sido, b.getBoundingClientRect()]);
                        const o = []; for (let i = 0; i < r.length; i++) for (let j = i + 1; j < r.length; j++) { const a = r[i][1], b = r[j][1];
                        if (a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom) o.push(r[i][0] + '-' + r[j][0]); } return o; }''')
                    self.assertEqual(overlap, [], f'{family}:{target} 배지 겹침')
                # 지자체 도청: 충남 도입, 전남광주는 두 청사 모두 → '광역 2/2', 경기 미도입
                page.locator('[data-rmap-switch="family"] button[data-value="eavesdrop"]').click()
                page.locator('[data-rmap-switch="target"] button[data-value="local"]').click()
                expect(page.locator('.rmap-badge[data-sido="44"]')).to_have_attribute('data-state', 'in')
                expect(page.locator('.rmap-badge[data-sido="12"]')).to_have_text('전남광주 2/2')
                expect(page.locator('.rmap-badge[data-sido="44"]')).to_have_text('충남도')
                expect(page.locator('.rmap-badge[data-sido="11"]')).to_have_text('서울시')
                expect(page.locator('.rmap-badge[data-sido="36"]')).to_have_text('세종시')
                expect(page.locator('.rmap-badge[data-sido="41"]')).to_have_attribute('data-state', 'out')
                # 배지가 화면에서 그 시·도 안에 있다
                box = page.locator('.rmap-badge[data-sido="44"]').bounding_box()
                hit = page.evaluate('([x, y]) => { const e = document.elementsFromPoint(x, y).find(n => n.classList && n.classList.contains("rmap-unit")); return e && e.dataset.sido; }',
                                    [box['x'] + box['width'] / 2, box['y'] + box['height'] / 2])
                self.assertEqual(hit, '44')
                # 배지를 누르면 광역 기관 카드(19:50)
                page.locator('.rmap-badge[data-sido="44"]').click()
                expect(page.locator('[data-rmap-card]')).to_be_visible()
                expect(page.locator('[data-rmap-card] [data-field="name"]')).to_have_text('충청남도')
                expect(page.locator('[data-rmap-card] .rmap-mark')).to_have_text('S')
                page.keyboard.press('Escape')
                page.locator('.rmap-badge[data-sido="41"]').click()
                expect(page.locator('[data-rmap-card] [data-field="status"]')).to_have_text('미도입')
                page.keyboard.press('Escape')
                self.assertEqual(page.locator('.rmap-badge .rmap-badge-dot').count(), 0)  # 점 없음
                expect(page.locator('.rmap-badge[data-sido="44"]')).to_have_css('color', 'rgb(255, 255, 255)')  # 채움 = 흰 글씨
                # 시·도 화면: 광역 상태 카드
                page.locator('.rmap-sido-row[data-sido="44"]').click()
                # 고른 시·도는 테두리 강조 대신 그림자(19:50)
                expect(page.locator('.rmap-sido-shadow')).not_to_have_css('display', 'none')
                expect(page.locator('.rmap-sido-shadow')).to_have_attribute('filter', 'url(#rmap-shadow)')  # 20:20: 폰(사파리)에서도 보이게 SVG 필터
                self.assertTrue(page.locator('.rmap-sido-shadow').get_attribute('d'))
                self.assertEqual(page.locator('.rmap-selected .rmap-unit').count(), page.locator('.rmap-unit[data-sido="44"]').count())
                expect(page.locator('.rmap-sido.is-selected')).to_have_css('stroke-width', '1.1px')
                titles = page.eval_on_selector_all('.rmap-section-title', 'els => els.map(e => e.firstChild.textContent)')
                self.assertLess(titles.index('도입한 곳'), titles.index('빠진 곳'))  # 도입한 곳이 위
                card = page.locator('[data-rmap-wide-card="in"]')
                expect(card).to_have_count(1)
                expect(card).to_contain_text('충청남도')
                expect(card.locator('[data-field="status"]')).to_have_text('도입')
                expect(card.locator('.rmap-mark')).to_have_text('S')
                expect(page.locator('.rmap-badges')).to_be_hidden()  # 시·도를 고르면(확대) 배지는 사라지고 카드로 본다
                page.locator('[data-rmap-back]').click()
                page.locator('.rmap-sido-row[data-sido="26"]').click()
                out = page.locator('[data-rmap-wide-card="out"]')
                expect(out).to_have_count(1)
                expect(out).to_contain_text('부산광역시')
                expect(out.locator('[data-field="status"]')).to_have_text('미도입')
                # 광역 보기(17:34): 시·도 전체 면을 광역 도입으로, 2칸 중 1칸은 흐리게. 목록은 광역 기관 카드. 기초 = 원래 보기
                page.locator('[data-rmap-back]').click()
                expect(page.locator('.rmap-badges')).to_be_visible()
                p = payload['combos']['eavesdrop:local']
                wide_btn, basic_btn = page.locator('[data-rmap-part="wide"]'), page.locator('[data-rmap-part="basic"]')
                wide_btn.click()
                expect(wide_btn).to_have_attribute('aria-pressed', 'true')
                expect(page.locator('[data-rmap-national] strong')).to_have_text(str(p['national']['wide']['adopted']))
                full = {r['code'] for r in p['sido'] if r['wide_count'] >= r['wide_slots']}
                units = payload['units']
                self.assertEqual(self.painted(page), {c for c, u in units.items() if u['sido'] in full})  # 충남·전남광주 전체 면
                expect(page.locator('.rmap-badges')).to_be_visible()
                cards = page.locator('[data-rmap-wide-list] [data-rmap-wide-card]')
                expect(cards).to_have_count(p['national']['wide']['total'])  # 17칸
                expect(page.locator('[data-rmap-wide-list] [data-rmap-wide-card="in"]')).to_have_count(p['national']['wide']['adopted'])
                expect(page.locator('[data-rmap-wide-list] [data-rmap-wide-card="in"][data-sido="44"] .rmap-mark')).to_have_text('S')
                expect(page.locator('.rmap-sido-row')).to_have_count(0)  # 막대 목록 대신 카드
                basic_btn.click()  # 기초 = 원래 보기로, 눌린 상태는 남기지 않는다
                expect(wide_btn).to_have_attribute('aria-pressed', 'false')
                self.assertIsNone(basic_btn.get_attribute('aria-pressed'))
                expect(page.locator('[data-rmap-national] strong')).to_have_text(str(p['national']['adopted']))
                expect(page.locator('.rmap-badges')).to_be_visible()
                expect(page.locator('.rmap-sido-row')).to_have_count(16)
                self.assertEqual(self.painted(page), {'44130'})
                # 광역 보기에서 카드를 누르면 그 시·도로(광역 보기는 꺼진다)
                wide_btn.click()
                page.locator('[data-rmap-wide-list] [data-sido="44"]').click()
                expect(page.locator('[data-rmap]')).to_have_attribute('data-sido', '44')
                self.assertEqual(self.painted(page), {'44130'})
            finally:
                browser.close()

    def test_free_zoom_sea_click_labels_and_hover(self):
        # 11d(형우 16:00~17:50): 휠·끌기·두 손가락·−/+·전국, 바다 → 전국, 확대하면 시군구 이름, 마우스 올리면 면 색만 바뀜
        sea = '''() => { const s = document.querySelector('[data-rmap-canvas] svg'), r = s.getBoundingClientRect();
            for (let i = 1; i < 30; i++) for (let j = 1; j < 30; j++) { const x = r.x + r.width * i / 30, y = r.y + r.height * j / 30;
              if (document.elementFromPoint(x, y) === s) return [x, y]; } return null; }'''
        vbw = '() => +document.querySelector("[data-rmap-canvas] svg").getAttribute("viewBox").split(" ")[2]'
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 900})
                self.open_map(page)
                root, svg = page.locator('[data-rmap]'), page.locator('[data-rmap-canvas] svg')
                expect(svg).to_have_css('touch-action', 'none')  # 20:07: 전국 크기에서도 지도 위 한 손가락 = 지도 이동
                # 마우스를 올리면 면 색만 진해지고 테두리 두께는 그대로
                xy = page.evaluate(POINT_INSIDE, '.rmap-unit[data-code="47130"]')
                page.mouse.move(*xy)
                expect(page.locator('.rmap-unit[data-code="47130"]')).to_have_css('fill', 'rgb(188, 199, 211)')
                expect(page.locator('.rmap-unit[data-code="47130"]')).to_have_css('stroke-width', '0.7px')
                # 휠 확대: 보기만 바뀌고 패널은 그대로. 광역 배지는 사라지고 시군구 이름이 나온다
                w0 = page.evaluate(vbw)
                box = svg.bounding_box()
                page.mouse.move(box['x'] + box['width'] * 0.6, box['y'] + box['height'] * 0.35)
                for _ in range(5):
                    page.mouse.wheel(0, -240)
                expect(root).to_have_attribute('data-zoomed', '1')
                self.assertLess(page.evaluate(vbw), w0 / 2)
                expect(root).to_have_attribute('data-sido', '')
                expect(page.locator('.rmap-sido-row')).to_have_count(16)
                expect(page.locator('.rmap-badges')).to_be_hidden()
                expect(page.locator('.rmap-label').first).to_be_visible()
                # 끌어서 이동: 보기는 옮겨지고 누름(시·도 선택·카드)은 생기지 않는다
                before = svg.get_attribute('viewBox')
                cx, cy = box['x'] + box['width'] * 0.6, box['y'] + box['height'] * 0.5
                page.mouse.move(cx, cy); page.mouse.down(); page.mouse.move(cx + 120, cy + 40, steps=8); page.mouse.up()
                self.assertNotEqual(svg.get_attribute('viewBox'), before)
                expect(root).to_have_attribute('data-sido', '')
                expect(page.locator('[data-rmap-card]')).to_be_hidden()
                # 확대 중 면을 누르면 패널만 그 시·도로, 보기는 그대로, 카드가 열린다
                sido = page.evaluate('() => document.elementFromPoint(%f, %f).dataset.sido' % (cx, cy))
                self.assertTrue(sido)
                before = svg.get_attribute('viewBox')
                page.mouse.click(cx, cy)
                expect(root).to_have_attribute('data-sido', sido)
                self.assertEqual(svg.get_attribute('viewBox'), before)
                expect(page.locator('[data-rmap-card]')).to_be_visible()
                # 바다를 누르면 전국으로. 8배 넘게 확대해 내륙만 보이면 바다가 없으므로 1.6배로 다시 맞추고 시·도를 고른 뒤 누른다
                page.locator('[data-rmap-zoom="전국 보기"]').click()
                expect(root).to_have_attribute('data-zoom', 'done')
                page.locator('[data-rmap-zoom="확대"]').click()
                expect(root).to_have_attribute('data-zoomed', '1')
                page.mouse.click(*page.evaluate(POINT_INSIDE, '.rmap-unit[data-code="44130"]'))
                expect(root).to_have_attribute('data-sido', '44')
                pt = page.evaluate(sea)
                self.assertIsNotNone(pt)
                page.mouse.click(*pt)
                expect(root).to_have_attribute('data-sido', '')
                expect(root).to_have_attribute('data-zoom', 'done')
                expect(root).to_have_attribute('data-zoomed', '')
                expect(page.locator('.rmap-badges')).to_be_visible()
                expect(page.locator('.rmap-labels')).to_be_hidden()
                # −/+·전국 버튼
                page.locator('[data-rmap-zoom="확대"]').click()
                expect(root).to_have_attribute('data-zoomed', '1')
                page.locator('[data-rmap-zoom="전국 보기"]').click()
                expect(root).to_have_attribute('data-zoom', 'done')
                expect(root).to_have_attribute('data-zoomed', '')
                page.locator('[data-rmap-zoom="축소"]').click()  # 전국보다 작게는 줄지 않는다
                self.assertAlmostEqual(page.evaluate(vbw), w0, delta=1)
                # 20:07: 전국 크기에서도 끌어서 옮긴다. 크기는 그대로, 배지는 계속 보이고, 바다를 누르면 제자리
                before = svg.get_attribute('viewBox')
                page.mouse.move(cx, cy); page.mouse.down(); page.mouse.move(cx + 90, cy + 30, steps=6); page.mouse.up()
                self.assertNotEqual(svg.get_attribute('viewBox'), before)
                self.assertAlmostEqual(page.evaluate(vbw), w0, delta=1)
                expect(page.locator('.rmap-badges')).to_be_visible()
                page.mouse.click(*page.evaluate(sea))
                expect(root).to_have_attribute('data-zoom', 'done')
                self.assertEqual(svg.get_attribute('viewBox'), before)
                # 두 손가락 벌리기(터치 포인터 두 개)
                page.evaluate('''() => { const s = document.querySelector('[data-rmap-canvas] svg'), r = s.getBoundingClientRect();
                    const cx = r.x + r.width * 0.6, cy = r.y + r.height * 0.5, o = {bubbles: true, pointerType: 'touch'};
                    s.dispatchEvent(new PointerEvent('pointerdown', {...o, pointerId: 11, clientX: cx - 20, clientY: cy}));
                    s.dispatchEvent(new PointerEvent('pointerdown', {...o, pointerId: 12, clientX: cx + 20, clientY: cy}));
                    for (let i = 1; i <= 10; i++) {
                      window.dispatchEvent(new PointerEvent('pointermove', {...o, pointerId: 11, clientX: cx - 20 - i * 8, clientY: cy}));
                      window.dispatchEvent(new PointerEvent('pointermove', {...o, pointerId: 12, clientX: cx + 20 + i * 8, clientY: cy})); }
                    window.dispatchEvent(new PointerEvent('pointerup', {...o, pointerId: 11})); window.dispatchEvent(new PointerEvent('pointerup', {...o, pointerId: 12})); }''')
                self.assertLess(page.evaluate(vbw), w0 / 3)
                # 시·도를 고르면 그 시·도 이름만
                page.locator('[data-rmap-zoom="전국 보기"]').click()
                page.locator('.rmap-sido-row[data-sido="44"]').click()
                expect(root).to_have_attribute('data-zoom', 'done')
                names = page.eval_on_selector_all('.rmap-label', 'els => els.map(e => e.dataset.unit)')
                self.assertTrue(names and all(n.startswith('44') for n in names), names)
                fs_sido = float(page.eval_on_selector('.rmap-label', 'e => getComputedStyle(e).fontSize').replace('px', ''))
                page.mouse.move(box['x'] + box['width'] * 0.6, box['y'] + box['height'] * 0.5)
                for _ in range(3):
                    page.mouse.wheel(0, -240)
                page.wait_for_timeout(400)
                fs_more = float(page.eval_on_selector('.rmap-label', 'e => getComputedStyle(e).fontSize').replace('px', ''))
                self.assertGreater(fs_more, fs_sido)  # 더 확대하면 글씨도 커진다
                self.assertLessEqual(fs_more, 16)
                page.close()
                # 폰(18:13 형우): 자리가 되는 만큼 시군구 이름. 11px, 아래 시트·확대 버튼에 가리는 이름은 없다
                page = browser.new_page(viewport={'width': 390, 'height': 844}, has_touch=True)
                self.open_map(page)
                # 20:10: 폰에서 두 손가락이 광역 배지 위에서 시작해도 지도가 확대되고(페이지 전체가 확대되지 않음), 카드는 열리지 않는다
                w_phone = page.evaluate(vbw)
                page.evaluate('''() => { const s = document.querySelector('[data-rmap-canvas] svg'), b = document.querySelector('.rmap-badge[data-sido="44"]').getBoundingClientRect();
                    const x = b.x + b.width / 2, y = b.y + b.height / 2, o = {bubbles: true, pointerType: 'touch'};
                    document.querySelector('.rmap-badge[data-sido="44"]').dispatchEvent(new PointerEvent('pointerdown', {...o, pointerId: 21, clientX: x, clientY: y}));
                    s.dispatchEvent(new PointerEvent('pointerdown', {...o, pointerId: 22, clientX: x + 40, clientY: y}));
                    for (let i = 1; i <= 12; i++) {
                      window.dispatchEvent(new PointerEvent('pointermove', {...o, pointerId: 21, clientX: x - i * 5, clientY: y}));
                      window.dispatchEvent(new PointerEvent('pointermove', {...o, pointerId: 22, clientX: x + 40 + i * 5, clientY: y})); }
                    window.dispatchEvent(new PointerEvent('pointerup', {...o, pointerId: 21}));
                    window.dispatchEvent(new PointerEvent('pointerup', {...o, pointerId: 22})); }''')
                self.assertLess(page.evaluate(vbw), w_phone / 2.5)
                expect(page.locator('[data-rmap-card]')).to_be_hidden()
                expect(page.locator('.rmap-canvas')).to_have_css('touch-action', 'none')
                page.locator('[data-rmap-zoom="전국 보기"]').tap()
                expect(page.locator('[data-rmap]')).to_have_attribute('data-zoom', 'done')
                page.locator('[data-rmap-sheet-toggle]').tap()
                page.locator('.rmap-sido-row[data-sido="44"]').tap()
                expect(page.locator('[data-rmap]')).to_have_attribute('data-zoom', 'done')
                expect(page.locator('.rmap-label').first).to_be_visible()
                fs = float(page.eval_on_selector('.rmap-label', 'e => getComputedStyle(e).fontSize').replace('px', ''))
                self.assertTrue(9 <= fs <= 15, fs)  # 19:32: 확대 정도에 따라 자동(폰은 1px 작게)
                hidden_by = page.evaluate('''() => { const covers = [...document.querySelectorAll('[data-rmap-panel], .rmap-zoom')].map(n => n.getBoundingClientRect());
                    return [...document.querySelectorAll('.rmap-label')].filter(l => { const r = l.getBoundingClientRect();
                      return covers.some(c => r.left < c.right && c.left < r.right && r.top < c.bottom && c.top < r.bottom); }).map(l => l.textContent); }''')
                self.assertEqual(hidden_by, [])
                page.close()
            finally:
                browser.close()

    def test_national_view_centers_the_peninsula(self):
        # 19:50 형우: 폰은 본토(울릉·독도 제외) 가운데를 화면 가운데에, 데스크톱은 원래대로(울릉·독도까지 넣은 전체)
        gap_js = '''() => { const u = [...document.querySelectorAll('.rmap-unit')].filter(p => p.dataset.code !== '47940').map(p => p.getBoundingClientRect());
            const l = Math.min(...u.map(r => r.left)), r = Math.max(...u.map(r => r.right)); return [l, window.innerWidth - r]; }'''
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 390, 'height': 844}, has_touch=True)
                self.open_map(page)
                gap = page.evaluate(gap_js)
                # 20:05·20:07 형우: 정가운데면 오른쪽으로 보여 왼쪽으로 약 26px — 오른쪽 여백이 왼쪽보다 40~70px 넓게
                self.assertTrue(40 <= gap[1] - gap[0] <= 70, f'폰 좌우 여백 {gap}')
                page.close()
                for width, height in ((1440, 900), (1280, 800)):
                    page = browser.new_page(viewport={'width': width, 'height': height})
                    self.open_map(page)
                    ul = page.locator('.rmap-unit[data-code="47940"]').bounding_box()
                    self.assertLessEqual(ul['x'] + ul['width'], width - 40 + 1)  # 울릉·독도도 빈 곳 안에
                    page.close()
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
                    # 11d부터 지도(svg)는 패널·띠 밑까지 깔리므로, 전국 지도 그림(면 묶음)이 띠·패널과 겹치지 않는지 본다
                    bar = page.locator('[data-rmap-bar]').bounding_box()
                    panel = page.locator('[data-rmap-panel]').bounding_box()
                    drawn = page.evaluate('() => { const r = document.querySelector("[data-rmap-canvas] svg g").getBoundingClientRect(); return {x: r.x, y: r.y, w: r.width, h: r.height}; }')
                    self.assertLessEqual(bar['y'] + bar['height'], drawn['y'] + 1)
                    self.assertLessEqual(panel['x'] + panel['width'], drawn['x'] + 1)
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
                    # 모바일 v5(18:45 형우): 머리띠 한 줄(☰), 전환은 지도 위 한 줄, 지도 자리가 화면의 60% 이상
                    self.assertLessEqual(page.locator('.topbar').bounding_box()['height'], 56, where)
                    expect(page.locator('.topbar nav')).to_be_hidden()
                    menu = page.locator('[data-rmap-menu]')
                    mb = menu.bounding_box()
                    self.assertGreaterEqual(min(mb['width'], mb['height']), 44, where)
                    menu.tap()
                    expect(page.locator('.topbar nav a', has_text='지역 현황')).to_be_visible()
                    menu.tap()
                    expect(page.locator('.topbar nav')).to_be_hidden()
                    sw = page.eval_on_selector_all('[data-rmap-switch]', 'els => els.map(e => Math.round(e.getBoundingClientRect().top))')
                    self.assertEqual(len(set(sw)), 1, f'{where} 전환 두 개가 한 줄이 아님')
                    expect(page.locator('.rmap-heading')).to_be_hidden()
                    free = page.evaluate('''() => document.querySelector('[data-rmap-panel]').getBoundingClientRect().top
                                             - document.querySelector('[data-rmap-bar]').getBoundingClientRect().bottom''')
                    self.assertGreaterEqual(free, height * 0.6, f'{where} 지도 자리 {free}px')
                    # 손잡이를 끌어 올리면 '전부', 끌어 내리면 '접힘'
                    def drag(dy):
                        hb = toggle.bounding_box()
                        x, y = hb['x'] + hb['width'] / 2, hb['y'] + hb['height'] / 2
                        page.evaluate('''([x, y, dy]) => { const h = document.querySelector('[data-rmap-sheet-toggle]'), o = {bubbles: true, pointerId: 31, pointerType: 'touch'};
                            h.dispatchEvent(new PointerEvent('pointerdown', {...o, clientX: x, clientY: y}));
                            for (let i = 1; i <= 10; i++) h.dispatchEvent(new PointerEvent('pointermove', {...o, clientX: x, clientY: y + dy * i / 10}));
                            h.dispatchEvent(new PointerEvent('pointerup', {...o, clientX: x, clientY: y + dy})); }''', [x, y, dy])
                    drag(-height)
                    expect(root).to_have_attribute('data-sheet', 'full')
                    expect(page.locator('.rmap-sido-row').first).to_be_visible()
                    drag(height)
                    expect(root).to_have_attribute('data-sheet', 'closed')
                    # 손잡이가 아니라 요약 숫자 쪽을 끌어도 시트가 올라간다(19:50)
                    def drag_from(sel, dy):
                        hb = page.locator(sel).bounding_box()
                        x, y = hb['x'] + 20, hb['y'] + hb['height'] / 2
                        page.evaluate('''([sel, x, y, dy]) => { const h = document.querySelector(sel), o = {bubbles: true, pointerId: 32, pointerType: 'touch'};
                            h.dispatchEvent(new PointerEvent('pointerdown', {...o, clientX: x, clientY: y}));
                            for (let i = 1; i <= 10; i++) window.dispatchEvent(new PointerEvent('pointermove', {...o, clientX: x, clientY: y + dy * i / 10}));
                            window.dispatchEvent(new PointerEvent('pointerup', {...o, clientX: x, clientY: y + dy})); }''', [sel, x, y, dy])
                    drag_from('[data-rmap-national]', -height)
                    expect(root).to_have_attribute('data-sheet', 'full')
                    drag_from('[data-rmap-national]', height)
                    expect(root).to_have_attribute('data-sheet', 'closed')
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
                    drag_from('[data-rmap-national]', -height // 2)  # 카드가 떠 있을 때 시트를 끌어 올리면 카드는 사라진다(19:50)
                    expect(card).to_be_hidden()
                    drag_from('[data-rmap-national]', height)
                    expect(root).to_have_attribute('data-sheet', 'closed')
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
