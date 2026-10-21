"""지역 현황 지도 계산 규칙(5단계). DB를 쓰지 않는다."""
from datetime import date
from unittest import TestCase

from delivery.domain.region_map import CAMERA, EAVESDROP, compute_map, family_of_marker


def rec(name, location, kind='admin', contracts=(), public=True, listed=True, logo=''):
    return {'id': name, 'name': name, 'location': location, 'type': kind, 'public': public, 'listed': listed,
            'logo': logo, 'contracts': list(contracts)}


def k(marker, product, active=True, d=date(2022, 5, 1)):
    return {'active': active, 'date': d, 'marker': marker, 'product': product}


S, C, D, H = ('S', 'Alpha-S'), ('C', 'Alpha-C'), ('D', 'Smart-D'), ('H', 'Alpha-H')
CHEONAN, ASAN, GONGJU, CHUNGNAM = '44130', '44200', '44150', '44'


class FamilyScenarios(TestCase):
    def test_family_bundles(self):
        for m in 'ISBDP':
            self.assertEqual(family_of_marker(m), EAVESDROP)
        self.assertEqual(family_of_marker('C'), CAMERA)
        self.assertIsNone(family_of_marker('H'))


class ComputeMapScenarios(TestCase):
    def test_ended_contract_is_not_adopted(self):
        m = compute_map([rec('천안시', CHEONAN, contracts=[k(*S, active=False)])], EAVESDROP)
        self.assertEqual(m['units'][CHEONAN]['state'], 'out')
        self.assertIn(CHEONAN, m['sido'][[s['code'] for s in m['sido']].index(CHUNGNAM)]['missing'])

    def test_facility_only_unit_stays_out_but_carries_an_icon(self):
        m = compute_map([rec('천안 어떤 시설', CHEONAN, 'facility', [k(*C)])], CAMERA)
        slot = m['units'][CHEONAN]
        self.assertEqual(slot['state'], 'out')
        self.assertEqual([f['name'] for f in slot['facilities']], ['천안 어떤 시설'])
        self.assertEqual(m['national']['adopted'], 0)

    def test_facility_icon_follows_the_family(self):
        m = compute_map([rec('천안 어떤 시설', CHEONAN, 'facility', [k(*C)])], EAVESDROP)
        self.assertEqual(m['units'][CHEONAN]['facilities'], [])

    def test_products_outside_bundles_mean_not_adopted(self):
        m = compute_map([rec('천안시', CHEONAN, contracts=[k(*H)])], EAVESDROP)
        self.assertEqual(m['units'][CHEONAN]['state'], 'out')
        m = compute_map([rec('천안시', CHEONAN, contracts=[k(*H)])], CAMERA)
        self.assertEqual(m['units'][CHEONAN]['state'], 'out')

    def test_smart_d_alone_counts_for_eavesdrop(self):
        m = compute_map([rec('천안시', CHEONAN, contracts=[k(*D)])], EAVESDROP)
        self.assertEqual(m['units'][CHEONAN]['state'], 'in')

    def test_year_is_the_earliest_active_contract(self):
        m = compute_map([rec('천안시', CHEONAN, contracts=[k(*S, d=date(2023, 1, 1)), k(*D, d=date(2019, 7, 1))])], EAVESDROP)
        org = m['units'][CHEONAN]['orgs'][0]
        self.assertEqual(org['year'], '2019')
        self.assertEqual(org['products'], 'Alpha-S, Smart-D')
        self.assertEqual(org['markers'], ['S', 'D'])
        self.assertEqual(org['marker_colors'], {'S': '#6B7580', 'D': '#6B7580'})  # 색 없음 → 기본 회색

    def test_marker_colors_come_from_the_product(self):
        line = dict(k(*S), color='#1E88E5')
        bad = dict(k(*D), color='red; background:url(x)')
        org = compute_map([rec('천안시', CHEONAN, contracts=[line, bad])], EAVESDROP)['units'][CHEONAN]['orgs'][0]
        self.assertEqual(org['marker_colors'], {'S': '#1E88E5', 'D': '#6B7580'})

    def test_any_undated_active_contract_hides_the_year(self):
        m = compute_map([rec('천안시', CHEONAN, contracts=[k(*S, d=date(2023, 1, 1)), k(*S, d=None)])], EAVESDROP)
        self.assertEqual(m['units'][CHEONAN]['orgs'][0]['year'], '—')

    def test_sido_offices_stay_out_of_counts_and_show_on_the_wide_line(self):
        m = compute_map([rec('충청남도', CHUNGNAM, contracts=[k(*S)])], EAVESDROP)
        chungnam = m['sido'][[s['code'] for s in m['sido']].index(CHUNGNAM)]
        self.assertEqual([o['name'] for o in chungnam['wide_orgs']], ['충청남도'])
        self.assertEqual(chungnam['adopted'], 0)
        # spec v4 7: 광역 기관은 기초 숫자에서 빠지고 광역 숫자로 센다
        self.assertTrue(chungnam['wide_adopted'])
        self.assertEqual(m['national']['basic']['adopted'], 0)
        self.assertEqual(m['national']['wide']['adopted'], 1)
        self.assertEqual(m['national']['adopted'], 1)

    def test_sejong_office_paints_its_single_unit_once(self):
        # 리뷰 24(2026-10-21 형우 승인): 세종·제주 기관은 도입한 곳 목록에만 두고 광역 줄에 다시 넣지 않는다
        m = compute_map([rec('세종특별자치시', '36110', contracts=[k('P', 'Alpha-P')])], EAVESDROP)
        sejong = m['sido'][[s['code'] for s in m['sido']].index('36')]
        self.assertEqual((sejong['adopted'], sejong['total']), (1, 1))
        self.assertTrue(sejong['whole'])
        self.assertEqual(sejong['wide_orgs'], [])
        self.assertEqual([o['name'] for o in m['units']['36110']['orgs']], ['세종특별자치시'])
        # spec v4 7: 세종은 기초가 없어 광역으로만 센다
        self.assertTrue(sejong['wide_adopted'])
        self.assertEqual((sejong['basic_adopted'], sejong['basic_total']), (0, 0))
        self.assertEqual(m['national']['wide'], {'adopted': 1, 'total': 16})
        self.assertEqual(m['national']['basic'], {'adopted': 0, 'total': 227})

    def test_national_equals_sum_of_sido(self):
        recs = [rec('천안시', CHEONAN, contracts=[k(*S)]), rec('아산시', ASAN, contracts=[k(*S)]),
                rec('공주시', GONGJU, contracts=[k(*C)])]
        m = compute_map(recs, EAVESDROP)
        # spec v4 7(2026-10-21 형우): 전국 = 광역 16 + 기초 227 = 243 (이전: 면 229)
        self.assertEqual(m['national']['basic']['adopted'], sum(s['basic_adopted'] for s in m['sido']))
        self.assertEqual(m['national'], {'adopted': 2, 'total': 243,
                                         'wide': {'adopted': 0, 'total': 16}, 'basic': {'adopted': 2, 'total': 227}})
        self.assertEqual(sum(s['total'] for s in m['sido']), 229)  # 지도 면은 그대로 229

    def test_jeonnam_gwangju_counts_two_wide_slots_for_local(self):
        # 형우 16:10: 전남광주는 광주청사·무안청사 2곳으로 센다. 분모도 2칸(광역 17)
        recs = [rec('전남광주통합특별시 광주청사', '12', contracts=[k(*S)]),
                rec('전남광주통합특별시 무안청사', '12', contracts=[k(*S)])]
        m = compute_map(recs, EAVESDROP, {'12': 2})
        self.assertEqual(m['national']['wide'], {'adopted': 2, 'total': 17})
        self.assertEqual(m['national']['total'], 244)
        m = compute_map(recs[:1], EAVESDROP, {'12': 2})
        self.assertEqual(m['national']['wide'], {'adopted': 1, 'total': 17})
        m = compute_map(recs, EAVESDROP)  # 칸 지정이 없으면 1칸
        self.assertEqual(m['national']['wide'], {'adopted': 1, 'total': 16})

    def test_jeju_office_counts_as_wide_and_other_offices_add_up(self):
        recs = [rec('제주특별자치도', '50000', contracts=[k(*S)]), rec('충청남도', CHUNGNAM, contracts=[k(*S)]),
                rec('천안시', CHEONAN, contracts=[k(*S)]), rec('충청남도 산림자원연구소', CHUNGNAM, 'facility', [k(*S)])]
        m = compute_map(recs, EAVESDROP)
        self.assertEqual(m['national']['wide']['adopted'], 2)   # 제주 + 충남(시설은 세지 않음)
        self.assertEqual(m['national']['basic']['adopted'], 1)  # 천안
        self.assertEqual(m['national']['adopted'], 3)
        jeju = m['sido'][[s['code'] for s in m['sido']].index('50')]
        self.assertEqual((jeju['basic_adopted'], jeju['basic_total']), (0, 0))

    def test_private_or_unlisted_records_are_left_out(self):
        recs = [rec('천안시', CHEONAN, contracts=[k(*S)], public=False),
                rec('아산시', ASAN, contracts=[k(*S)], listed=False)]
        m = compute_map(recs, EAVESDROP)
        self.assertEqual(m['national']['adopted'], 0)

    def test_records_without_location_are_reported_as_unassigned(self):
        m = compute_map([rec('어딘가 시청', '', contracts=[k(*S)])], EAVESDROP)
        self.assertEqual([o['name'] for o in m['unassigned']], ['어딘가 시청'])
        self.assertEqual(m['national']['adopted'], 0)

    def test_card_has_exactly_the_four_fields_plus_identity(self):
        m = compute_map([rec('천안시', CHEONAN, contracts=[k(*S)])], EAVESDROP)
        org = m['units'][CHEONAN]['orgs'][0]
        # spec v4 6(형우 16:13): 화면은 제품명 대신 마킹 글자를 쓴다. 금액·수량·연락처 같은 내부 정보는 여전히 없다
        self.assertEqual(set(org), {'id', 'name', 'initial', 'logo', 'products', 'markers', 'marker_colors', 'year'})
        self.assertEqual(org['initial'], '천')
