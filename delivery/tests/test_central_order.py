"""중앙정부 나열 순서(2026-10-22 형우): 청와대 → 국회 → 헌법기관 → 대통령·총리 소속 → 행정각부(정부조직법 제29조), 각 부 뒤에 소속 기관.
앞으로 등록하는 기관도 같은 기준(목록 자리, 없으면 이름으로 소속 묶음 끝, 그래도 없으면 맨 끝)."""
from tempfile import TemporaryDirectory
from django.test import SimpleTestCase, TestCase, override_settings
from delivery.domain.central_order import central_block, central_sort_key, name_order_key
from delivery.models import Product
from .test_performance_look import make_customer, make_user

APPROVED = ('청와대, 대한민국 국회, 헌법재판소, 중앙선거관리위원회, 감사원, 고위공직자범죄수사처, 국무총리실, 식품의약품안전처, 금융위원회, '
            '국세청, 조달청, 과학기술정보통신부, 우정사업본부, 교육부, 교원소청심사위원회, 국립특수교육원, 중앙교육연수원, 외교부, 통일부, '
            '법무부, 공소청, 국방부, 합동참모본부, 육군, 해군, 해병대, 공군, 전략사령부, 드론작전사령부, 국방부조사본부, 한미연합군사령부, '
            '행정안전부 정부청사관리본부, 서울청사관리소, 대전청사관리소, 국가정보자원관리원, 대통령기록관, 경찰청, 경찰인재개발원, 경찰수사연수원, '
            '국립중앙도서관, 국립중앙박물관, 조선왕릉동부지구관리소, 창경궁 관리소, 농림축산식품부, 국립농산물품질관리원, 농림축산검역본부, '
            '국립종자원, 농식품공무원교육원, 농촌진흥청, 국립농업과학원, 국립원예특작과학원, 산림청, 산업통상부, 보건복지부, 고용노동부, '
            '행정중심복합도시건설청, 해양수산부, 해양경찰청, 해양경찰정비창').split(', ')


class CentralOrderUnit(SimpleTestCase):
    def test_current_59_follow_the_approved_order(self):
        self.assertEqual(len(APPROVED), 59)
        self.assertEqual(sorted(reversed(APPROVED), key=central_sort_key), APPROVED)

    def test_new_names_join_their_ministry_block_or_go_last(self):
        order = sorted(APPROVED + ['소방청', '해군작전사령부', '관세청', '국립수산과학원', '가상 신규 기관', '서울경찰청'], key=central_sort_key)
        self.assertEqual(order.index('관세청'), order.index('국세청') + 1)                        # 목록 자리
        self.assertEqual(order.index('해군작전사령부'), order.index('한미연합군사령부') + 1)        # 국방부 묶음 끝
        self.assertGreater(order.index('서울경찰청'), order.index('경찰수사연수원'))                # 행정안전부 묶음 안
        self.assertLess(order.index('서울경찰청'), order.index('국립중앙도서관'))
        self.assertEqual(central_block('국립수산과학원'), 'mof')
        self.assertEqual(order[-1], '가상 신규 기관')                                             # 어디에도 안 맞으면 맨 끝
        self.assertEqual(name_order_key('public', '나 기관'), (0, 0, '나 기관'))                  # 다른 분류는 가나다순


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class CentralOrderHttp(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = make_user('central-employee', 'employee')
        product = Product.objects.create(code='central-p', name='중앙 가상 P', marker='P')
        for name in ['감사원', '대한민국 국회', '청와대', '경찰청', '가 가상 공공기관']:
            make_customer(name, 'public' if name.startswith('가 ') else 'central', product=product)

    def test_screen_and_print_use_the_same_central_order(self):
        self.enterContext(override_settings(MEDIA_ROOT=self.enterContext(TemporaryDirectory())))
        self.client.force_login(self.employee)
        screen = self.client.get('/performance/')
        central = [item['name'] for group in screen.context['list_groups'] if group['code'] == 'central' for item in group['items']]
        self.assertEqual(central, ['청와대', '대한민국 국회', '감사원', '경찰청'])
        printed = self.client.get('/performance/print/')
        names = [card['name'] for group in printed.context['groups'] if group['label'] == '중앙정부' for row in group['rows'] for card in row]
        self.assertEqual(names, ['청와대', '대한민국 국회', '감사원', '경찰청'])


class PrivateOrderUnit(SimpleTestCase):
    """민간(2026-10-22 형우): 재계순위(공정위 2026 공시대상기업집단) → 그룹 안 대표 계열사 먼저·나머지 가나다 → 순위 밖 가나다."""

    def test_groups_by_ranking_flagship_first_and_unranked_last(self):
        from delivery.domain.private_order import private_group
        names = ['효성', '현대엘리베이터', 'SK 텔레콤', '에스원', '삼성SDS', '삼성전자', 'SK 하이닉스', '㈜LG', 'LG 화학',
                 '현대건설', '현대자동차', '대한항공', '가 가상 민간', 'JTBC', '중앙그룹']
        order = sorted(names, key=lambda n: name_order_key('private', n))
        self.assertEqual(order, ['삼성전자', '삼성SDS', '에스원', 'SK 하이닉스', 'SK 텔레콤', '현대자동차', '현대건설', '㈜LG', 'LG 화학',
                                 '대한항공', '효성', '중앙그룹', 'JTBC', '가 가상 민간', '현대엘리베이터'])
        self.assertEqual(private_group('삼성바이오로직스'), '삼성')     # 앞으로 등록하는 계열사도 이름으로 그룹을 찾는다
        self.assertEqual(private_group('이마트'), '신세계')
        self.assertIsNone(private_group('현대엘리베이터'))             # 현대그룹은 2026 순위 밖(현대자동차그룹 아님)


def _unit(sido, name):
    from delivery.domain import admin_areas as aa
    return next(code for code, unit_name, unit_sido, _whole in aa.UNITS if unit_sido == sido and unit_name == name)


class LocalOrderUnit(SimpleTestCase):
    """지자체·의회(2026-10-22 형우): 시·도 차례로, 시·도 안에서 광역 → 광역 소속 시설·공기업 → 기초 가나다. 소재지 모름은 끝."""

    def test_sido_then_tier_then_name(self):
        from delivery.domain.local_order import local_sort_key
        rows = [('경기도', '41', 'admin'), ('가평군', _unit('41', '가평군'), 'admin'), ('경기주택도시공사', '41', 'facility'),
                ('서울특별시 강남구', _unit('11', '강남구'), 'admin'), ('서울특별시', '11', 'admin'),
                ('서울특별시립 아동힐링센터', '11', 'facility'), ('인천광역시', '28', 'admin'), ('소재지 모름', '', '')]
        self.assertEqual([r[0] for r in sorted(rows, key=lambda r: local_sort_key(*r))],
                         ['서울특별시', '서울특별시립 아동힐링센터', '서울특별시 강남구', '인천광역시', '경기도', '경기주택도시공사', '가평군', '소재지 모름'])


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class LocalOrderHttp(TestCase):
    @classmethod
    def setUpTestData(cls):
        from delivery.models import Customer
        cls.employee = make_user('local-order-employee', 'employee')
        product = Product.objects.create(code='local-order-p', name='지자체 가상 P', marker='P')
        for name, code, kind in [('가평군', _unit('41', '가평군'), 'admin'), ('경기도', '41', 'admin'),
                                 ('경기주택도시공사', '41', 'facility'), ('서울특별시 강남구', _unit('11', '강남구'), 'admin'),
                                 ('서울특별시', '11', 'admin')]:
            customer = make_customer(name, 'local', 'capital', product=product)
            Customer.objects.filter(pk=customer.pk).update(location_code=code, institution_type=kind)

    def test_screen_and_print_put_province_first(self):
        self.enterContext(override_settings(MEDIA_ROOT=self.enterContext(TemporaryDirectory())))
        self.client.force_login(self.employee)
        expected = ['서울특별시', '서울특별시 강남구', '경기도', '경기주택도시공사', '가평군']
        screen = self.client.get('/performance/')
        self.assertEqual([item['name'] for group in screen.context['list_groups'] if group['code'] == 'local' for item in group['items']], expected)
        printed = self.client.get('/performance/print/')
        self.assertEqual([card['name'] for group in printed.context['groups'] if group['label'].startswith('지방자치단체') for row in group['rows'] for card in row], expected)
