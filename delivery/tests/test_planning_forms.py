from io import BytesIO
from PIL import Image
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from delivery.forms import LogoField, PresentationForm, WholeQuantityField


def image_upload(format='PNG', name='logo.png'):
    data = BytesIO()
    Image.new('RGB', (3, 3), 'white').save(data, format=format)
    return SimpleUploadedFile(name, data.getvalue())


class PlanningInputScenarios(SimpleTestCase):
    def test_png_jpg_allowed_and_wrong_format_or_large_file_rejected(self):
        field = LogoField(required=False)
        self.assertIsNotNone(field.clean(image_upload()))
        self.assertIsNotNone(field.clean(image_upload('JPEG', 'logo.jpg')))
        for upload in [image_upload('GIF', 'logo.png'), image_upload('WEBP', 'logo.webp'),
                       SimpleUploadedFile('large.png', b'x' * (2 * 1024 * 1024 + 1))]:
            with self.subTest(name=upload.name), self.assertRaises(ValidationError):
                field.clean(upload)

    def test_optional_fields_blank_but_region_required_for_local_and_council(self):
        data = {'official_name': '가상 기관', 'category': 'public', 'display_as': 'customer', 'partner_public': 'default'}
        self.assertTrue(PresentationForm(data).is_valid())
        for category in ['local', 'council']:
            with self.subTest(category=category):
                form = PresentationForm({**data, 'category': category})
                self.assertFalse(form.is_valid())
                self.assertIn('region', form.errors)

    def test_quantities_not_coerced_and_error_is_actionable(self):
        for value in ['0', '-1', '1.5', '', '1e2']:
            with self.subTest(value=value), self.assertRaisesMessage(ValidationError, '1 이상의 정수'):
                WholeQuantityField().clean(value)
        self.assertEqual(WholeQuantityField().clean('15'), 15)

    def test_logo_remove_and_replace_cannot_be_requested_together(self):
        form = PresentationForm({'official_name': '가상 기관', 'category': 'public', 'display_as': 'customer',
                                 'partner_public': 'default', 'remove_logo': 'on'}, {'logo': image_upload()})
        self.assertFalse(form.is_valid())
        self.assertIn('logo', form.errors)
