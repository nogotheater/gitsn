"""3단계 fill_locations: 대조표는 DB를 바꾸지 않고, 확인(Y)한 줄만 반영한다."""
import csv
import tempfile
from datetime import date
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from delivery.models import Category, Contract, ContractProduct, Customer, Organization, Product, Region


class FillLocationsScenarios(TestCase):
    @classmethod
    def setUpTestData(cls):
        s = Product.objects.create(code='fl-s', name='가상 S', marker='S')
        def make(name, region, category=Category.LOCAL):
            c = Customer.objects.create(organization=Organization.objects.create(official_name=name),
                                        category=category, region=region, partner_public=True)
            k = Contract.objects.create(customer=c, contracting_party=c.organization, is_active=True,
                                        contract_date=date(2025, 3, 1))
            ContractProduct.objects.create(contract=k, product=s, quantity=1)
            return c
        cls.cheonan = make('천안시청', Region.CHUNGCHEONG)
        cls.hall = make('세종문화회관', Region.CAPITAL)
        cls.other = Customer.objects.create(organization=Organization.objects.create(official_name='가상 공공기관'),
                                            category=Category.PUBLIC, partner_public=True)

    def run_report(self, d):
        call_command('fill_locations', report=d, stdout=StringIO())
        with open(Path(d) / '03_location_review.csv', newline='', encoding='utf-8-sig') as f:
            return list(csv.DictReader(f))

    def write(self, d, rows):
        p = Path(d) / 'checked.csv'
        with open(p, 'w', newline='', encoding='utf-8-sig') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
        return p

    def test_report_lists_only_local_and_council_and_changes_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            rows = self.run_report(d)
            self.assertEqual({r['기관명'] for r in rows}, {'천안시청', '세종문화회관'})
            self.assertTrue((Path(d) / '03_location_review.html').exists())
        self.assertFalse(Customer.objects.exclude(location_code='').exists())

    def test_only_confirmed_rows_are_applied(self):
        with tempfile.TemporaryDirectory() as d:
            rows = self.run_report(d)
            for r in rows:
                if r['기관명'] == '세종문화회관':
                    r['확정_소재지'], r['확인'] = '서울', 'Y'
            call_command('fill_locations', apply=self.write(d, rows), stdout=StringIO())
        self.hall.refresh_from_db(); self.cheonan.refresh_from_db()
        self.assertEqual((self.hall.location_code, self.hall.institution_type), ('11', 'facility'))
        self.assertEqual(self.cheonan.location_code, '')  # 확인 없음 → 그대로

    def test_unknown_place_stops_the_whole_apply(self):
        with tempfile.TemporaryDirectory() as d:
            rows = self.run_report(d)
            for r in rows:
                r['확인'] = 'Y'
                if r['기관명'] == '세종문화회관':
                    r['확정_소재지'] = '인천 중구'   # 개편으로 없어진 이름
            with self.assertRaises(CommandError):
                call_command('fill_locations', apply=self.write(d, rows), stdout=StringIO())
        self.assertFalse(Customer.objects.exclude(location_code='').exists())
