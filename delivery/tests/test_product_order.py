from importlib import import_module

from django.apps import apps
from django.test import SimpleTestCase, TestCase

from delivery.domain.products import PRODUCT_ORDER, marker_rank, ordered_products, product_sort_key
from delivery.models import Product


class ProductOrderTests(SimpleTestCase):
    """2026-10-22 형우: 제품은 어디서나 I, S, B, D, P, H, C 순서."""

    def test_order_and_unknown_markers_last(self):
        self.assertEqual(PRODUCT_ORDER, ('I', 'S', 'B', 'D', 'P', 'H', 'C'))
        markers = ['C', 'H', 'x', 'P', 'D', 'b', 'S', 'I', '']
        ordered = sorted(markers, key=lambda m: product_sort_key(m, m))
        self.assertEqual(ordered[:7], ['I', 'S', 'b', 'D', 'P', 'H', 'C'])
        self.assertEqual(marker_rank('x'), len(PRODUCT_ORDER))


class ProductLabelTests(SimpleTestCase):
    def test_short_model_name_whichever_field_holds_it(self):
        from delivery.domain.products import short_and_long
        self.assertEqual(short_and_long('Alpha-C', '불법촬영 탐지 시스템 Alpha-C'), ('Alpha-C', '불법촬영 탐지 시스템'))
        self.assertEqual(short_and_long('상시형 무선도청 탐지 시스템', 'Alpha-S'), ('Alpha-S', '상시형 무선도청 탐지 시스템'))
        self.assertEqual(short_and_long('Alpha-H', ''), ('Alpha-H', ''))


class ProductOrderDbTests(TestCase):
    def test_querysets_and_s_color_for_b_and_d(self):
        for marker, color in (('C', '#D84A4A'), ('H', '#7A55C2'), ('P', '#2E9B5F'), ('D', '#999999'), ('B', '#888888'), ('S', '#2F7FD0'), ('I', '#1F4E9A')):
            Product.objects.create(code=f'order-{marker}', name=f'순서 가상 {marker}', marker=marker, color=color)
        self.assertEqual([p.marker for p in ordered_products(Product.objects.all())], ['I', 'S', 'B', 'D', 'P', 'H', 'C'])
        migration = import_module('delivery.migrations.0007_product_marker_colors')
        migration.match_s_color(apps, None)
        colors = {p.marker: p.color for p in Product.objects.all()}
        self.assertEqual(colors['B'], '#2F7FD0')
        self.assertEqual(colors['D'], '#2F7FD0')
        self.assertEqual(colors['C'], '#D84A4A')
