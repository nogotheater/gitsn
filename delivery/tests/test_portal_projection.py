"""Real overview template/view projection using synthetic, already-filtered data."""
import re
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID
from django import forms
from django.test import SimpleTestCase, RequestFactory
from delivery.domain.audience import TargetRecord, ProductBadge, project_targets
from delivery.models import Category
from delivery.portal_forms import PerformanceFilterForm
from delivery.portal_views import performance
from delivery.templatetags.delivery_display import versioned_static


PRODUCTS = [SimpleNamespace(pk=UUID(int=index), code=code) for index, code in enumerate(['Alpha-I', 'Alpha-P', 'Alpha-S'], 1)]


class ProjectionFilterForm(PerformanceFilterForm):
    products = forms.MultipleChoiceField(required=False, choices=[(str(p.pk), p.code) for p in PRODUCTS], widget=forms.CheckboxSelectMultiple)

    def clean_products(self):
        return [p for p in PRODUCTS if str(p.pk) in self.cleaned_data['products']]

    def product_catalog(self):
        return [{'id': str(p.pk), 'name': p.code, 'code': p.code, 'marker': p.code[-1], 'color': ''} for p in PRODUCTS]


class OverviewProjectionScenarios(SimpleTestCase):
    def test_asset_urls_refresh_by_content_and_the_real_page_uses_them(self):
        with TemporaryDirectory() as folder:
            css = Path(folder) / 'portal.css'
            css.write_text('old version')
            with patch('delivery.templatetags.delivery_display.finders.find', return_value=str(css)):
                first = versioned_static('delivery/portal.css')
                self.assertEqual(first, versioned_static('delivery/portal.css'))
                css.write_text('new version')  # Same size and path; bytes determine the key.
                second = versioned_static('delivery/portal.css')
            self.assertNotEqual(first, second)
        html = self.response([self.record(1)]).content.decode()
        self.assertIn('delivery/portal.css?v=', html)
        self.assertIn('delivery/planning.css?v=', html)
        self.assertIn('delivery/performance.js?v=', html)
        self.assertNotIn('delivery/portal.css"', html)

    def response(self, records, *, audience='partner', query=None):
        user = SimpleNamespace(is_authenticated=True, is_active=True, delivery_access=SimpleNamespace(audience=audience), has_perm=lambda _: False)
        request = RequestFactory().get('/performance/', query or {})
        request.user = user
        payload = project_targets(records, audience=audience, category_codes=Category.values)
        with patch('delivery.portal_views.PerformanceFilterForm', ProjectionFilterForm), patch('delivery.portal_views.current_performance_payload', return_value=deepcopy(payload)):
            return performance(request)

    def record(self, index, category='public', public=True, counted=True):
        return TargetRecord(id=str(UUID(int=100 + index)), kind='customer', category=category, region='',
                            show_in_list=True, include_in_total=counted, partner_public=public,
                            name='SECRET_PROJECTION_SENTINEL' if not public else f'가상 고객사 {index:02}',
                            products=tuple(ProductBadge(str(p.pk), p.code, p.code[-1], '#0474D4') for p in PRODUCTS))

    def test_private_only_category_is_small_note_without_identity_or_global_metric(self):
        response = self.response([self.record(1), self.record(2, 'private', False)])
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('비공개 1곳 포함', html)
        self.assertNotIn('SECRET_PROJECTION_SENTINEL', html)
        self.assertNotIn(str(UUID(int=102)), html)
        self.assertNotIn('count-secondary', html)
        self.assertIn('<title>납품현황 · GITSN</title>', html)
        self.assertNotIn('>실적 현황<', html)

    def test_selected_products_and_categories_project_into_sections_and_canonical_links(self):
        response = self.response([self.record(1)], query={'products': [str(PRODUCTS[0].pk), str(PRODUCTS[1].pk)], 'category': ['public', 'finance']})
        html = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(html.count('product-mark is-selected'), 2)
        self.assertEqual(html.count('product-mark is-subdued'), 1)
        self.assertIn('하나 이상 도입', html)
        self.assertIn('data-category="public"', html)
        self.assertIn('category=public', html)
        self.assertIn('category=finance', html)
        self.assertIn('공공기관, 금융', html)
        print_links = re.findall(r'/performance/print/\?([^"]*)"', html)
        self.assertTrue(print_links)
        self.assertTrue(all('q=' not in link and 'category=public' in link for link in print_links))

    def test_all_rows_render_once_on_one_screen_in_category_order(self):
        # 2026-10-22 형우: 페이지 없음(기준 변경 이유). 접기는 화면(CSS)에서만 하고 카드는 모두 그린다.
        records = [self.record(index, 'central') for index in range(26)] + [self.record(30, 'education')]
        html = self.response(records, audience='employee').content.decode()
        self.assertEqual(html.count('class="customer-card"'), 27)
        self.assertNotIn('— 계속', html)
        self.assertLess(html.index('id="section-central"'), html.index('id="section-education"'))
        for index in range(26):
            self.assertEqual(html.count(f'<h3>가상 고객사 {index:02}</h3>'), 1)
