"""고객사 관리 기간 보기(2026-11-17 형우: '추가된 고객사를 월별로', '등록월, 계약월 기준을 둘 다',
'드롭다운 보다는 다른형태로' → 시안 7: 열두 달 막대 위에 '계약 N건 / 신규 N곳', (나) 계약 N건 = 기존 고객사의 추가 계약 건수)."""
from datetime import date, datetime
from unittest import mock
from zoneinfo import ZoneInfo
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import SimpleTestCase, TestCase, override_settings
from delivery.models import Contract, ContractProduct, Customer, Organization, Product, UserAccessProfile
from delivery.services.customer_months import chart

SEOUL = ZoneInfo('Asia/Seoul')
TODAY = date(2026, 11, 17)


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CustomerPeriodScenarios(TestCase):
    @classmethod
    def setUpTestData(cls):
        user = get_user_model().objects.create_user('months-manager', password='LocalTestOnly!27')
        UserAccessProfile.objects.create(user=user, audience='employee')
        user.user_permissions.add(Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery'))
        cls.manager = user
        cls.c = Product.objects.create(code='months-c', name='가상 월 C', marker='C')

    def setUp(self):
        self.client.force_login(self.manager)
        patcher = mock.patch('django.utils.timezone.localdate', return_value=TODAY)
        patcher.start()
        self.addCleanup(patcher.stop)

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

    def test_registered_month_opens_on_this_month_with_day_groups(self):
        old = self.customer('월 기존 기관', (2026, 10, 1))                 # 처음 옮겨 온 자료
        self.contract(old, (2026, 10, 1), date(2025, 7, 16))
        self.contract(old, (2026, 11, 10), date(2026, 11, 3))              # 11월에 기존 고객사가 계약 추가
        new = self.customer('월 신규 기관', (2026, 11, 5))
        self.contract(new, (2026, 11, 5), date(2026, 10, 20))              # 11월에 새 고객사(계약은 10월) — '계약 N건'에 안 셈
        first = self.page()                                                 # 처음 열면 등록월 · 이번 달
        self.assertNotIn('<select id="basis"', first)
        self.assertIn('10월 23일부터(그 전은 기존 자료)', first)
        self.assertIn('계약 1건', first)
        self.assertIn('신규 1곳', first)
        self.assertIn('이번 달', first)
        self.assertIn('2026년 11월 등록 · 2곳', first)
        self.assertIn('신규 1', first)
        self.assertIn('계약 추가 1', first)
        self.assertLess(first.index('11월 10일'), first.index('11월 5일'))  # 날짜별로 묶고 최근 날짜 먼저
        self.assertIn('월 기존 기관', first)
        self.assertIn('월 신규 기관', first)
        self.assertIn('기존 자료 1', first)
        self.assertNotIn('등록 자료 <strong>', first)
        only_new = self.page(basis='registered', month='2026-11', kind='new')
        self.assertIn('월 신규 기관', only_new)
        self.assertNotIn('월 기존 기관', only_new)
        everything = self.page(basis='registered', month='all')
        self.assertIn('등록 자료 <strong>2</strong>개', everything)
        self.assertNotIn('✕ 기간 해제', everything)
        base = self.page(basis='registered', month='base')
        self.assertIn('기존 자료(2026.10.22까지 처음 입력) · 1곳', base)
        self.assertIn('월 기존 기관', base)
        self.assertNotIn('월 신규 기관', base)
        self.assertIn('이 해에는 처음 입력한 기존 자료만 있습니다', self.page(basis='registered', year=2025, month='all'))

    def test_contract_month_counts_added_contracts_and_collects_missing_dates(self):
        a = self.customer('월 계약 기관', (2026, 10, 1))
        self.contract(a, (2026, 10, 1), date(2025, 7, 16))
        self.contract(a, (2026, 11, 10), date(2026, 11, 3))
        self.contract(a, (2026, 11, 11), date(2026, 11, 4))                 # 같은 고객사가 한 달에 두 건 → 계약 2건, 1곳
        b = self.customer('월 날짜없음 기관', (2026, 11, 12))
        self.contract(b, (2026, 11, 12), None)
        listing = self.page(basis='contract', year=2026, month='all')
        self.assertIn('계약 2건', listing)
        self.assertNotIn('신규 1곳', listing)
        self.assertIn('⚠ 계약일 미입력 1', listing)
        self.assertIn('>2025</a>', listing)
        self.assertIn('신규 1곳', self.page(basis='contract', year=2025, month='all'))
        november = self.page(basis='contract', month='2026-11')
        self.assertIn('2026년 11월 계약 · 1곳', november)
        self.assertIn('2026.11.04 계약', november)
        self.assertNotIn('월 날짜없음 기관', november)
        self.assertNotIn('period-day', november)                            # 계약월은 날짜 묶음 대신 카드에 계약일
        missing = self.page(basis='contract', month='nodate')
        self.assertIn('계약일 미입력 · 1곳', missing)
        self.assertIn('월 날짜없음 기관', missing)
        self.assertNotIn('월 계약 기관', missing)
        self.assertIn('월 계약 기관', self.page(basis='contract', month='1999-01'))   # 없는 달은 무시하고 전체


class CustomerPeriodChart(SimpleTestCase):
    def test_bar_heights_share_one_scale_and_future_months_stay_empty(self):
        stats = {'2026-03': {'new': 2, 'added': 1, 'contracts': 2}, '2026-06': {'new': 1, 'added': 0, 'contracts': 0}}
        months, first = chart(stats, 'contract', 2026, '2026-03', TODAY, lambda key: key)
        self.assertEqual(first, 1)
        self.assertEqual(len(months), 12)
        march, june, december = months[2], months[5], months[11]
        self.assertEqual((march['height'], march['h_new'], march['h_added']), (150, 75, 75))
        self.assertEqual(june['height'], 38)
        self.assertTrue(march['selected'])
        self.assertTrue(december['future'])
        self.assertTrue(months[10]['current'])
        registered, first = chart({}, 'registered', 2026, '', TODAY, lambda key: key)
        self.assertEqual((first, len(registered)), (10, 3))
        self.assertEqual(chart({}, 'registered', 2025, '', TODAY, lambda key: key)[0], [])
