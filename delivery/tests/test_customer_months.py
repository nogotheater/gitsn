"""고객사 관리 월별 보기(2026-11-17 형우: '추가된 고객사를 월별로', '등록월, 계약월 기준을 둘 다')."""
from datetime import date, datetime
from zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from delivery.models import Contract, ContractProduct, Customer, Organization, Product, UserAccessProfile

SEOUL = ZoneInfo('Asia/Seoul')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CustomerMonthScenarios(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_user('months-manager', password='LocalTestOnly!27')
        UserAccessProfile.objects.create(user=user, audience='employee')
        user.user_permissions.add(Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery'))
        cls.manager = user
        cls.c = Product.objects.create(code='months-c', name='가상 월 C', marker='C')

    def setUp(self):
        self.client.force_login(self.manager)

    def customer(self, name, created):
        customer = Customer.objects.create(organization=Organization.objects.create(official_name=name), category='public', partner_public=True)
        Customer.objects.filter(pk=customer.pk).update(created_at=datetime(*created, 10, tzinfo=SEOUL))
        return customer

    def contract(self, customer, created, contract_date=None):
        contract = Contract.objects.create(customer=customer, contracting_party=customer.organization, is_active=True, contract_date=contract_date)
        ContractProduct.objects.create(contract=contract, product=self.c, quantity=1)
        Contract.objects.filter(pk=contract.pk).update(created_at=datetime(*created, 10, tzinfo=SEOUL))
        return contract

    def page(self, **query):
        return self.client.get('/planning/', query).content.decode()

    def test_registered_month_separates_new_customers_added_contracts_and_the_first_import(self):
        old = self.customer('월 기존 기관', (2026, 10, 1))                 # 처음 옮겨 온 자료
        self.contract(old, (2026, 10, 1), date(2025, 7, 16))
        self.contract(old, (2026, 11, 10), date(2026, 11, 3))              # 11월에 계약 추가
        new = self.customer('월 신규 기관', (2026, 11, 5))
        self.contract(new, (2026, 11, 5), date(2026, 10, 20))              # 11월에 새 고객사(계약은 10월)
        listing = self.page(basis='registered')
        self.assertIn('2026년 11월 · 신규 1 · 계약 추가 1', listing)
        self.assertIn('기존 자료(2026.10.22까지 처음 입력) · 1곳', listing)
        november = self.page(basis='registered', month='2026-11')
        self.assertIn('월 신규 기관', november)
        self.assertIn('월 기존 기관', november)
        self.assertIn('신규 · 2026.11.05 등록', november)
        self.assertIn('계약 추가 · 2026.11.10 등록', november)
        only_new = self.page(basis='registered', month='2026-11', kind='new')
        self.assertIn('월 신규 기관', only_new)
        self.assertNotIn('월 기존 기관', only_new)

    def test_contract_month_uses_contract_dates_and_collects_missing_dates(self):
        a = self.customer('월 계약 기관', (2026, 10, 1))
        self.contract(a, (2026, 10, 1), date(2025, 7, 16))
        self.contract(a, (2026, 11, 10), date(2026, 11, 3))
        b = self.customer('월 날짜없음 기관', (2026, 11, 12))
        self.contract(b, (2026, 11, 12), None)
        listing = self.page(basis='contract')
        self.assertIn('2025년 7월 · 신규 1', listing)
        self.assertIn('2026년 11월 · 신규 0 · 계약 추가 1', listing)
        self.assertIn('계약일 미입력 · 1곳', listing)
        november = self.page(basis='contract', month='2026-11')
        self.assertIn('계약 추가 · 2026.11.03 계약', november)
        self.assertNotIn('월 날짜없음 기관', november)
        missing = self.page(basis='contract', month='nodate')
        self.assertIn('월 날짜없음 기관', missing)
        self.assertNotIn('월 계약 기관', missing)
        self.assertIn('월 계약 기관', self.page(basis='contract', month='1999-01'))   # 없는 달은 무시하고 전체
