from tempfile import TemporaryDirectory
import re
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from delivery.models import Customer, Organization, Contract, ContractProduct, Product, UserAccessProfile
from .test_planning_forms import image_upload


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PrintingHttpScenarios(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = get_user_model().objects.create_user('print-employee', password='LocalPrintExample!81')
        cls.partner = get_user_model().objects.create_user('print-partner', password='LocalPrintExample!81')
        UserAccessProfile.objects.create(user=cls.employee, audience='employee')
        UserAccessProfile.objects.create(user=cls.partner, audience='partner')
        cls.c = Product.objects.create(code='Alpha-C', name='불법촬영 탐지 시스템 Alpha-C', marker='C')
        cls.i = Product.objects.create(code='Alpha-I', name='가상 제품 I', marker='I')
        cls.public = cls.customer('공개 가상 고객사', True)
        cls.private = cls.customer('PRINT_PRIVATE_SENTINEL', False)
        cls.contract(cls.public, cls.c)
        cls.contract(cls.public, cls.i)
        cls.contract(cls.private, cls.c)

    @staticmethod
    def customer(name, public):
        return Customer.objects.create(organization=Organization.objects.create(official_name=name), category='public', partner_public=public, memo='PRINT_MEMO_SENTINEL')

    @staticmethod
    def contract(customer, product):
        contract = Contract.objects.create(customer=customer, contracting_party=customer.organization, is_active=True, source_email_subject='PRINT_SOURCE_SENTINEL')
        ContractProduct.objects.create(contract=contract, product=product, quantity=19)
        return contract

    def setUp(self):
        folder = self.enterContext(TemporaryDirectory())
        self.enterContext(override_settings(MEDIA_ROOT=folder))

    def get_preview(self, user, **query):
        self.client.force_login(user)
        return self.client.get('/performance/print/', query)

    def test_employee_selects_public_private_or_all_and_counts_follow_scope(self):
        for scope, total, public_visible, private_visible in [('public', 1, True, False), ('private', 1, False, True), ('all', 2, True, True)]:
            response = self.get_preview(self.employee, scope=scope)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['counts']['total'], total)
            self.assertEqual('공개 가상 고객사' in response.content.decode(), public_visible)
            self.assertEqual('PRINT_PRIVATE_SENTINEL' in response.content.decode(), private_visible)
        self.assertEqual(self.get_preview(self.employee).context['scope_form'].data['scope'], 'all')
        all_scope = self.get_preview(self.employee, scope='all')
        self.assertNotContains(all_scope, '공개 1곳')
        self.assertNotContains(all_scope, '비공개 실적')
        self.assertNotContains(all_scope, '공개·비공개 모두 · 자료 작성일')

    def test_partner_keeps_private_counts_without_names_and_cannot_expand_output_scope(self):
        response = self.get_preview(self.partner)
        self.assertEqual(response.context['counts']['total'], 2)
        self.assertEqual(response.context['counts']['private'], 1)
        self.assertContains(response, '비공개 실적 1곳 포함')
        for value in ['PRINT_PRIVATE_SENTINEL', str(self.private.pk), 'PRINT_SOURCE_SENTINEL', 'PRINT_MEMO_SENTINEL', 'name="scope"']:
            self.assertNotContains(response, value)
        for route in ['/performance/print/', '/performance/print/pdf/']:
            for scope in ['public', 'private']:
                self.assertEqual(self.client.get(route, {'scope': scope}).status_code, 403)

    def test_product_and_filters_use_all_live_contracts_without_marker_or_source_output(self):
        response = self.get_preview(self.employee, scope='all', products=[str(self.c.pk), str(self.i.pk)])
        self.assertEqual(response.context['counts']['total'], 2)
        heading = re.search(r'<h1>(.*?)</h1>', response.content.decode(), re.S)
        self.assertIsNotNone(heading)
        self.assertEqual(heading[1], 'Alpha-I, Alpha-C 고객사')   # 2026-10-22 형우: '도입' 없이, 제품 순서(I, S, B, D, P, H, C)
        self.assertEqual(response.context['selected_products'], [str(self.c.pk), str(self.i.pk)])
        reverse = self.get_preview(self.employee, scope='all', products=[str(self.i.pk), str(self.c.pk)])
        self.assertEqual(reverse.context['title'], 'Alpha-I, Alpha-C 고객사')
        self.assertEqual(reverse.context['counts']['total'], 2)
        with patch('delivery.print_views.render_pdf', return_value=b'%PDF-1.7\nexample') as renderer:
            pdf_response = self.client.get('/performance/print/pdf/', {'scope': 'all', 'products': [str(self.c.pk), str(self.i.pk)]})
        self.assertEqual(pdf_response.status_code, 200)
        self.assertTrue(pdf_response['Content-Disposition'].startswith('attachment;'))
        with patch('delivery.print_views.render_pdf', return_value=b'%PDF-1.7\nexample'):
            inline = self.client.get('/performance/print/pdf/', {'scope': 'all', 'inline': '1'})
        self.assertTrue(inline['Content-Disposition'].startswith('inline;'))   # 폰 '인쇄'용(2026-10-22 형우)
        pdf_heading = re.search(r'<h1>(.*?)</h1>', renderer.call_args.args[0], re.S)
        self.assertIsNotNone(pdf_heading)
        self.assertEqual(pdf_heading[1], heading[1])
        for value in ['product-mark', 'PRINT_SOURCE_SENTINEL', 'PRINT_MEMO_SENTINEL', '19대', '표시 목록', '전체 지역', '금융 0곳']:
            self.assertNotContains(response, value)
        single = self.get_preview(self.employee, scope='public', products=[str(self.c.pk)])
        self.assertContains(single, '<h1>Alpha-C 고객사</h1>', html=True)
        self.assertNotContains(single, '자료 작성일')   # 2026-10-22 형우: 바닥 왼쪽 문구 삭제
        self.assertEqual(single.context['counts']['total'], 1)
        self.assertEqual(self.get_preview(self.employee, scope='public', category='local').context['counts']['total'], 0)

    def test_back_link_keeps_filters_and_chosen_category_is_not_repeated(self):
        # 2026-10-22 형우: '← 납품현황'은 고른 제품·분류 그대로, 고른 분류는 조건 줄에 다시 적지 않는다(분류별 숫자 줄에 이미 있음).
        response = self.get_preview(self.employee, scope='all', category='public', products=[str(self.c.pk)])
        self.assertContains(response, 'href="/performance/?products=%s&amp;category=public"' % self.c.pk)
        self.assertNotContains(response, 'class="conditions"')
        several = self.get_preview(self.employee, scope='all', products=[str(self.c.pk), str(self.i.pk)])
        self.assertContains(several, '<p class="conditions">선택 제품 중 하나 이상 도입</p>', html=True)

    def test_output_contains_all_filtered_rows_beyond_current_screen_page(self):
        for index in range(30):
            customer = self.customer(f'추가 가상 기관 {index:02}', True)
            self.contract(customer, self.c)
        response = self.get_preview(self.employee, scope='public', page='2')
        self.assertEqual(response.context['counts']['total'], 31)
        self.assertContains(response, '추가 가상 기관 00')
        self.assertContains(response, '추가 가상 기관 29')
        self.assertEqual(sum(len(row) for group in response.context['groups'] for row in group['rows']), 31)
        self.assertEqual([len(row) for row in response.context['groups'][0]['rows']], [4, 4, 4, 4, 4, 4, 4, 3])

    def test_any_product_and_several_categories_match_list_counts_and_pdf(self):
        query = {'products': [str(self.c.pk), str(self.i.pk)], 'category': ['public', 'education'], 'q': 'ignored-by-print'}
        self.client.force_login(self.partner)
        screen = self.client.get('/performance/', query)
        preview = self.client.get('/performance/print/', query)
        self.assertEqual(screen.context['counts'], preview.context['counts'])
        self.assertEqual(preview.context['counts']['total'], 2)
        self.assertEqual(preview.context['counts']['private'], 1)
        self.assertEqual(preview.context['selected_categories'], ['public', 'education'])
        self.assertIn('category=public', preview.context['query'])
        self.assertIn('category=education', preview.context['query'])
        self.assertNotIn('q=', preview.context['query'])
        # 2026-10-22 형우: 고른 분류는 조건 줄에 다시 적지 않는다 — 분류별 숫자 줄에 고른 분류만 나온다.
        self.assertNotContains(preview, '공공기관, 교육')
        self.assertEqual([row['label'] for row in preview.context['category_totals']], ['공공기관'])   # 0곳인 교육은 숫자 줄에 나오지 않는다(기존 규칙)
        self.assertNotContains(preview, 'PRINT_PRIVATE_SENTINEL')
        with patch('delivery.print_views.render_pdf', return_value=b'%PDF-1.7\nexample') as renderer:
            response = self.client.get('/performance/print/pdf/', query)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('PRINT_PRIVATE_SENTINEL', renderer.call_args.args[0])
        self.assertIn('비공개 실적 1곳 포함', renderer.call_args.args[0])

    def test_invalid_or_anonymous_requests_never_fall_back_to_full_output(self):
        self.assertRedirects(self.client.get('/performance/print/'), '/login/?next=/performance/print/')
        self.client.force_login(self.employee)
        for path in ['/performance/print/', '/performance/print/pdf/']:
            for query in [{'scope': 'bad'}, {'products': ['bad']}, {'category': 'bad'}, {'category': ['public', 'bad']}]:
                response = self.client.get(path, query)
                self.assertEqual(response.status_code, 400)
                self.assertNotContains(response, 'PRINT_PRIVATE_SENTINEL', status_code=400)
            self.assertEqual(self.client.post(path, {}).status_code, 405)

    def test_logos_are_inline_with_no_paths_or_arbitrary_remote_requests(self):
        self.public.logo.save('public-symbol.png', image_upload())
        self.private.logo.save('secret-symbol.png', image_upload())
        response = self.get_preview(self.partner)
        self.assertContains(response, 'data:image/png;base64,')
        for value in ['public-symbol.png', 'secret-symbol.png', '/media/', 'PRINT_PRIVATE_SENTINEL']:
            self.assertNotContains(response, value)
        self.assertIn('no-store', response['Cache-Control'])

    def test_pdf_uses_identical_authorized_template_and_strips_controls(self):
        self.client.force_login(self.partner)
        with patch('delivery.print_views.render_pdf', return_value=b'%PDF-1.7\nexample') as renderer:
            response = self.client.get('/performance/print/pdf/', {'products': [str(self.c.pk)], 'url': 'http://example.invalid/'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', response['Content-Disposition'])
        self.assertIn('no-store', response['Cache-Control'])
        html = renderer.call_args.args[0]
        self.assertIn('공개 가상 고객사', html)
        for value in ['PRINT_PRIVATE_SENTINEL', 'PRINT_SOURCE_SENTINEL', '<aside class="print-controls">', 'example.invalid', '<script>']:
            self.assertNotIn(value, html)

    def test_finished_contracts_are_not_printed_and_empty_output_is_clear(self):
        Contract.objects.filter(customer=self.public).update(is_active=False)
        response = self.get_preview(self.employee, scope='public')
        self.assertEqual(response.context['counts']['total'], 0)
        self.assertContains(response, '선택한 조건에 표시할 고객사가 없습니다')
        self.assertNotContains(response, '공개 가상 고객사')

    def test_user_names_are_escaped_and_pdf_errors_are_actionable(self):
        self.public.organization.official_name = '<script>untrusted()</script>'
        self.public.organization.save()
        response = self.get_preview(self.employee)
        self.assertContains(response, '&lt;script&gt;untrusted()&lt;/script&gt;')
        self.assertNotContains(response, '<script>untrusted()</script>')
        with patch('delivery.print_views.render_pdf', side_effect=RuntimeError('test rendering failure')), self.assertLogs('delivery.print_views', level='ERROR'):
            response = self.client.get('/performance/print/pdf/')
        self.assertContains(response, 'PDF를 만들지 못했습니다', status_code=503)
