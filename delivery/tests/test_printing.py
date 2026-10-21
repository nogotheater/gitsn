from io import BytesIO
from unittest.mock import Mock
from types import SimpleNamespace
from uuid import UUID
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import SimpleTestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from delivery.services.printing import logo_data, print_document
from delivery.print_views import OutputScopeForm, selected_product_order
from .test_planning_forms import image_upload


class PrintInputScenarios(SimpleTestCase):
    def test_title_order_preserves_validated_selection_despite_database_collation(self):
        c = SimpleNamespace(pk=UUID('aaaaaaaa-0000-0000-0000-000000000001'))
        i = SimpleNamespace(pk=UUID('bbbbbbbb-0000-0000-0000-000000000002'))
        for database_order in [[c, i], [i, c]]:
            with self.subTest(database_order=[str(p.pk) for p in database_order]):
                self.assertEqual(selected_product_order(database_order, [str(c.pk), str(i.pk)]), [c, i])
                self.assertEqual(selected_product_order(database_order, [str(i.pk), str(c.pk)]), [i, c])
                self.assertEqual(selected_product_order(database_order, [str(i.pk).upper(), str(i.pk), str(c.pk)]), [i, c])
        self.assertEqual(selected_product_order([], []), [])

    def test_scope_and_partner_boundary_reject_unsupported_choices(self):
        self.assertTrue(OutputScopeForm({'scope': 'public'}).is_valid())
        self.assertTrue(OutputScopeForm({'scope': 'private'}).is_valid())
        self.assertTrue(OutputScopeForm({'scope': 'all'}).is_valid())
        self.assertFalse(OutputScopeForm({'scope': 'invented'}).is_valid())
        partner = Mock(is_authenticated=True, is_active=True)
        partner.delivery_access.audience = 'partner'
        with self.assertRaises(PermissionDenied):
            print_document(partner, {}, 'private')
        with self.assertRaises(ValidationError):
            print_document(partner, {}, 'invented')

    def test_missing_or_invalid_logo_uses_default_and_never_an_external_url(self):
        self.assertEqual(logo_data(None), '')
        field = Mock()
        field.open.return_value.__enter__ = Mock(return_value=BytesIO(b'<svg>bad</svg>'))
        field.open.return_value.__exit__ = Mock(return_value=False)
        self.assertEqual(logo_data(field), '')

    def test_valid_logo_is_reencoded_as_inline_png(self):
        field = Mock()
        field.open.return_value.__enter__ = Mock(return_value=image_upload())
        field.open.return_value.__exit__ = Mock(return_value=False)
        self.assertTrue(logo_data(field).startswith('data:image/png;base64,'))
