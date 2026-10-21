"""지역 현황 지도 데이터(5단계)를 실제 DB 모델로 확인한다."""
from datetime import date

from django.test import TestCase

from delivery.models import Category, Contract, ContractProduct, Customer, Organization, Product, Region
from delivery.services.region_map import basis_date, region_map_payload


class RegionMapPayloadScenarios(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.s = Product.objects.create(code='rm-s', name='Alpha-S', marker='S')
        cls.c = Product.objects.create(code='rm-c', name='Alpha-C', marker='C')

        def make(name, category, loc, kind, *lines, public=True):
            cu = Customer.objects.create(organization=Organization.objects.create(official_name=name), category=category,
                                         region=Region.CHUNGCHEONG, partner_public=public,
                                         location_code=loc, institution_type=kind)
            for product, active, d in lines:
                ko = Contract.objects.create(customer=cu, contracting_party=cu.organization, is_active=active, contract_date=d)
                ContractProduct.objects.create(contract=ko, product=product, quantity=1)
            return cu
        make('천안시', Category.LOCAL, '44130', 'admin', (cls.s, True, date(2020, 1, 1)))
        make('아산시', Category.LOCAL, '44200', 'admin', (cls.c, True, None))
        make('천안시의회', Category.COUNCIL, '44130', 'admin', (cls.s, True, date(2021, 1, 1)))
        make('충청남도 산림자원연구소', Category.LOCAL, '44', 'facility', (cls.c, True, date(2024, 1, 1)))
        make('공주시', Category.LOCAL, '44150', 'admin', (cls.s, False, date(2018, 1, 1)))
        make('비공개 시청', Category.LOCAL, '44210', 'admin', (cls.s, True, date(2020, 1, 1)), public=False)
        make('소재지 없는 군청', Category.LOCAL, '', '', (cls.s, True, date(2020, 1, 1)))

    def test_four_combinations(self):
        p = region_map_payload()
        self.assertEqual(set(p['combos']), {'eavesdrop:local', 'eavesdrop:council', 'camera:local', 'camera:council'})
        self.assertEqual(len(p['units']), 229)
        self.assertEqual(len(p['sido']), 16)

    def test_values_per_combination(self):
        p = region_map_payload()
        el = p['combos']['eavesdrop:local']
        self.assertEqual(el['national']['adopted'], 1)            # 천안만 (공주 종료, 비공개 제외, 미지정 제외)
        self.assertEqual(el['units']['44130']['orgs'][0]['year'], '2020')
        self.assertEqual([o['name'] for o in el['unassigned']], ['소재지 없는 군청'])
        cl = p['combos']['camera:local']
        self.assertEqual(cl['units']['44200']['orgs'][0]['year'], '—')
        chungnam = [s for s in cl['sido'] if s['code'] == '44'][0]
        self.assertEqual([f['name'] for f in chungnam['wide_facilities']], ['충청남도 산림자원연구소'])
        self.assertEqual(p['combos']['eavesdrop:council']['national']['adopted'], 1)
        self.assertEqual(p['combos']['camera:council']['national']['adopted'], 0)

    def test_basis_date_is_latest_update(self):
        d = basis_date()
        self.assertIsNotNone(d)
        self.assertLessEqual(abs((d - date.today()).days), 1)
