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
                                              ('천안시의회', Category.COUNCIL, '44130', 'admin', s),
                                              ('충청남도', Category.LOCAL, '44', 'admin', s),
                                              ('전남광주통합특별시 광주청사', Category.LOCAL, '12', 'admin', s),
                                              ('전남광주통합특별시 무안청사', Category.LOCAL, '12', 'admin', s),
                                              ('공주 어떤 시설', Category.LOCAL, '44150', 'facility', c),
                                              ('충청남도 산림자원연구소', Category.LOCAL, '44', 'facility', c)]:
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
                s = sido('eavesdrop:local', '44')
                expect(page.locator('[data-rmap-national] strong')).to_have_text(str(s['adopted']))
                self.assertEqual(page.eval_on_selector_all('[data-rmap-missing] li', 'els => els.map(e => e.textContent)'),
                                 [names[c] for c in s['missing']])
                self.assertEqual(page.eval_on_selector_all('[data-rmap-adopted] .rmap-org-name', 'els => els.map(e => e.textContent)'), ['천안시'])
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
                # ← 전국
                page.locator('[data-rmap-back]').click()
                expect(root).to_have_attribute('data-sido', '')
                expect(page.locator('.rmap-sido-row')).to_have_count(16)
                # 전남광주 광역 줄은 여러 기관을 나열하고, Esc로 전국 복귀
                page.locator('[data-rmap-switch="family"] button[data-value="eavesdrop"]').click()
                page.locator('.rmap-sido-row[data-sido="12"]').click()
                expect(page.locator('[data-rmap-wide] [data-org]')).to_have_count(2)
                page.keyboard.press('Escape')
                expect(root).to_have_attribute('data-sido', '')
                # 지도 면을 눌러도 그 시·도로 간다
                page.locator('.rmap-unit[data-code="44130"]').click(force=True)
                expect(root).to_have_attribute('data-sido', '44')
            finally:
                browser.close()


    @staticmethod
    def click_unit(page, selector):
        """SVG 면의 테두리 상자 가운데가 이웃 면일 수 있으므로, 그 요소에 직접 클릭 이벤트를 보낸다."""
        page.eval_on_selector(selector, """el => { const r = el.getBoundingClientRect();
            el.dispatchEvent(new MouseEvent('click', {bubbles: true, clientX: r.x + r.width / 2, clientY: r.y + r.height / 2})); }""")

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
                page.eval_on_selector('.rmap-unit[data-code="44130"]', """el => { const r = el.getBoundingClientRect();
                    el.dispatchEvent(new PointerEvent('pointermove', {bubbles: true, pointerType: 'mouse', clientX: r.x + r.width / 2, clientY: r.y + r.height / 2})); }""")
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
                # 시설 표시는 제품군을 따라간다
                expect(page.locator('.rmap-fac')).to_have_count(0)
                expect(page.locator('[data-rmap-legend-fac]')).to_be_hidden()
                page.locator('[data-rmap-switch="family"] button[data-value="camera"]').click()
                expect(page.locator('.rmap-fac')).to_have_count(1)
                expect(page.locator('.rmap-fac')).to_have_attribute('data-code', '44150')
                expect(page.locator('[data-rmap-legend-fac]')).to_be_visible()
                expect(page.locator('[data-rmap-missing] li[data-unit="44150"] [data-fac]')).to_have_count(1)
                expect(page.locator('[data-rmap-wide] [data-fac]')).to_contain_text('충청남도 산림자원연구소')
                # 시설 표시를 누르면 카드에 시설·공기업 칸
                self.click_unit(page, '.rmap-fac[data-code="44150"]')
                expect(page.locator('[data-rmap-card-fac]')).to_contain_text('공주 어떤 시설')
                expect(page.locator('[data-rmap-card] [data-field="status"]')).to_have_text('미도입')
            finally:
                browser.close()
