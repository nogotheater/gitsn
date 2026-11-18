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

    def test_only_contract_month_remains_and_opens_on_this_month(self):
        # 2026-11-18 형우 "기간에서 등록월은 없애자. 계약월로만 보여도 될 것 같아" → 등록월 기준의 검사(날짜별 묶음, 기존 자료)는 뺐다
        old = self.customer('월 기존 기관', (2026, 10, 1))
        self.contract(old, (2026, 10, 1), date(2025, 7, 16))
        self.contract(old, (2026, 11, 10), date(2026, 11, 3))
        new = self.customer('월 신규 기관', (2026, 11, 5))
        self.contract(new, (2026, 11, 5), date(2026, 11, 12))
        first = self.page()                                                  # 처음 열면 이번 달(계약일 기준)
        self.assertNotIn('등록월', first)
        self.assertNotIn('기존 자료', first)
        self.assertIn('계약서의 계약일 기준', first)
        self.assertIn('2026년 11월 계약 · 2곳', first)
        self.assertIn('계약 1건', first)
        self.assertIn('신규 1곳', first)
        self.assertIn('이번 달', first)
        self.assertNotIn('period-day', first)
        self.assertIn('2026년 11월 계약 · 2곳', self.page(basis='registered', month='2026-11'))   # 예전 주소도 계약월로

    def test_bar_hover_lists_products_by_customer_category(self):
        # 2026-11-18 형우: 그래프에 마우스를 올리면 고객 분류별로 '중앙정부 I 몇 건 C 몇 건'
        i = Product.objects.create(code='months-i', name='가상 월 I', marker='I')
        ministry = Customer.objects.create(organization=Organization.objects.create(official_name='월 가상 부처'), category='central', partner_public=True)
        for products in ([self.c], [self.c, i]):
            contract = Contract.objects.create(customer=ministry, contracting_party=ministry.organization, is_active=True, contract_date=date(2026, 6, 3))
            for product in products:
                ContractProduct.objects.create(contract=contract, product=product, quantity=1)
        school = self.customer('월 가상 학교', (2026, 10, 1))
        school.category = 'education'
        school.save(update_fields=['category'])
        self.contract(school, (2026, 10, 1), date(2026, 6, 20))
        june = self.page(year=2026, month='all')
        tip = june[june.index('6월 <small>고객 분류별 제품'):]
        tip = tip[:tip.index('</a>')]
        self.assertLess(tip.index('중앙정부'), tip.index('교육'))
        self.assertLess(tip.index('>I</span>1건'), tip.index('>C</span>2건'))             # 제품 순서 I, S, B, D, P, H, C
        self.assertIn('>C</span>1건', tip[tip.index('교육'):])
        self.assertNotIn('7월 <small>고객 분류별 제품', june)

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


    def test_customer_with_an_undated_contract_is_not_counted_as_new_by_contract_month(self):
        # 2026-11-18 형우: 울산광역시(I 2026.10.15, C·S 계약일 미입력)가 10월 신규로 잡혔다 → 빈 계약이 더 먼저일 수 있으니 '계약 추가'
        ulsan = self.customer('월 날짜 섞인 기관', (2026, 10, 1))
        self.contract(ulsan, (2026, 10, 1), None)
        self.contract(ulsan, (2026, 10, 1), date(2026, 10, 15))
        listing = self.page(basis='contract', year=2026, month='all')
        self.assertIn('계약 1건', listing)
        self.assertNotIn('신규 1곳', listing)
        self.assertIn('⚠ 계약일 미입력 1', listing)
        october = self.page(basis='contract', month='2026-10')
        self.assertIn('2026년 10월 계약 · 1곳', october)
        self.assertIn('계약 추가 1', october)
        self.assertIn('신규 0', october)
        self.assertIn('2026.10.15 계약', october)

    @override_settings(PERFORMANCE_PAGE_CACHE=True)
    def test_list_reuses_its_material_until_data_changes(self):
        # 2026-11-17 형우 '고객사 관리 페이지가 좀 느린 것 같고' → 자료가 그대로면 다시 세지 않는다
        from delivery.services import customer_months, page_cache
        page_cache.clear()
        self.addCleanup(page_cache.clear)
        self.customer('월 캐시 기관', (2026, 11, 5))
        with mock.patch.object(customer_months, 'month_index', wraps=customer_months.month_index) as counted:
            self.assertIn('월 캐시 기관', self.page(month='all'))
            self.assertIn('월 캐시 기관', self.page(month='all'))
            self.assertEqual(counted.call_count, 1)
            self.customer('월 캐시 새 기관', (2026, 11, 6))
            self.assertIn('월 캐시 새 기관', self.page(month='all'))
            self.assertEqual(counted.call_count, 2)


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
