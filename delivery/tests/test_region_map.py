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

    def test_any_undated_active_contract_hides_the_year(self):
        m = compute_map([rec('천안시', CHEONAN, contracts=[k(*S, d=date(2023, 1, 1)), k(*S, d=None)])], EAVESDROP)
        self.assertEqual(m['units'][CHEONAN]['orgs'][0]['year'], '—')

    def test_sido_offices_stay_out_of_counts_and_show_on_the_wide_line(self):
        m = compute_map([rec('충청남도', CHUNGNAM, contracts=[k(*S)])], EAVESDROP)
        chungnam = m['sido'][[s['code'] for s in m['sido']].index(CHUNGNAM)]
        self.assertEqual([o['name'] for o in chungnam['wide_orgs']], ['충청남도'])
        self.assertEqual(chungnam['adopted'], 0)
        self.assertEqual(m['national']['adopted'], 0)

    def test_sejong_office_paints_its_single_unit_once(self):
        # 리뷰 24(2026-10-21 형우 승인): 세종·제주 기관은 도입한 곳 목록에만 두고 광역 줄에 다시 넣지 않는다
        m = compute_map([rec('세종특별자치시', '36110', contracts=[k('P', 'Alpha-P')])], EAVESDROP)
        sejong = m['sido'][[s['code'] for s in m['sido']].index('36')]
        self.assertEqual((sejong['adopted'], sejong['total']), (1, 1))
        self.assertTrue(sejong['whole'])
        self.assertEqual(sejong['wide_orgs'], [])
        self.assertEqual([o['name'] for o in m['units']['36110']['orgs']], ['세종특별자치시'])

    def test_national_equals_sum_of_sido(self):
        recs = [rec('천안시', CHEONAN, contracts=[k(*S)]), rec('아산시', ASAN, contracts=[k(*S)]),
                rec('공주시', GONGJU, contracts=[k(*C)])]
        m = compute_map(recs, EAVESDROP)
        self.assertEqual(m['national']['adopted'], sum(s['adopted'] for s in m['sido']))
        self.assertEqual(m['national'], {'adopted': 2, 'total': 229})
        self.assertEqual(sum(s['total'] for s in m['sido']), 229)

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
        self.assertEqual(set(org), {'id', 'name', 'initial', 'logo', 'products', 'year'})
        self.assertEqual(org['initial'], '천')
