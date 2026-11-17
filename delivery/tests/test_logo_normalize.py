"""심볼 자동 정리(2026-11-17 형우: '팀원이 올려도 로고 크기·여백이 통일되게', '우리가 심볼 형태로만 업로드').

기준: 2026-11-17에 잰 기존 심볼 104개 — 정사각 칸에 그림이 약 77%, 투명 배경.
새로 올리는 심볼만 자동 정리하고, 기존 심볼은 모양 그대로(용량만 줄임).
"""
from io import BytesIO
from tempfile import TemporaryDirectory
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image, ImageDraw
from delivery.models import Customer, LogoRendition, Organization, UserAccessProfile
from delivery.services.logo_normalize import TARGET, LIMIT, normalize
from delivery.services.logo_renditions import make, rendition_key


def drawn(size, background, shapes, mode='RGB'):
    image = Image.new(mode, size, background)
    draw = ImageDraw.Draw(image)
    for kind, box, fill in shapes:
        (draw.ellipse if kind == 'ellipse' else draw.rectangle)(box, fill=fill)
    return image


def art_box(canvas):
    return canvas.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox()


class NormalizeScenarios(SimpleTestCase):
    def test_white_background_is_removed_trimmed_and_centered_on_a_square_canvas(self):
        source = drawn((900, 300), 'white', [('ellipse', (100, 20, 360, 280), (4, 116, 212))])   # 흰 바탕 JPG에 꽉 잘리지 않은 원
        canvas, info = normalize(source)
        self.assertEqual(canvas.size, (512, 512))
        self.assertTrue(info['removed'])
        self.assertEqual(canvas.getpixel((2, 2))[3], 0)                   # 흰 배경은 투명
        left, top, right, bottom = art_box(canvas)
        self.assertLess(abs((left + right) / 2 - 256), 3)                 # 가운데
        self.assertLess(abs((top + bottom) / 2 - 256), 3)
        self.assertLess(abs((right - left) / 512 - TARGET), 0.04)          # 정사각에 가까운 심볼은 칸의 약 77%
        self.assertEqual(info['warnings'], [])

    def test_white_inside_the_symbol_is_kept(self):
        source = drawn((400, 400), 'white', [('ellipse', (40, 40, 360, 360), (200, 30, 40)), ('ellipse', (140, 140, 260, 260), 'white')])
        canvas, _ = normalize(source)
        self.assertEqual(canvas.getpixel((256, 256))[3], 255)              # 가운데 흰 원(심볼의 일부)은 남는다
        self.assertEqual(canvas.getpixel((256, 256))[:3], (255, 255, 255))

    def test_thin_outline_keeps_the_white_inside_on_a_large_original(self):
        # 큰 원본은 거친 격자에서 배경을 찾는다(2026-11-17, 무료 서버 속도). 가는 테두리도 벽으로 남아 안쪽 흰색이 새지 않는다.
        source = Image.new('RGB', (2000, 2000), 'white')
        draw = ImageDraw.Draw(source)
        draw.ellipse((200, 200, 1800, 1800), outline=(0, 0, 0), width=3)
        draw.rectangle((900, 900, 1100, 1100), fill=(0, 80, 160))
        canvas, info = normalize(source)
        self.assertEqual(canvas.getpixel((256, 200))[3], 255)   # 테두리 안쪽 흰 부분
        self.assertEqual(canvas.getpixel((3, 3))[3], 0)         # 바깥 흰 배경
        self.assertLess(abs(info['art_px'][0] - 1601), 8)       # 경고 판단은 원본 크기 기준

    def test_tight_and_loose_crops_end_up_the_same_size(self):
        tight = drawn((300, 300), (0, 0, 0, 0), [('ellipse', (0, 0, 299, 299), (20, 120, 60, 255))], 'RGBA')
        loose = drawn((900, 900), (0, 0, 0, 0), [('ellipse', (300, 300, 599, 599), (20, 120, 60, 255))], 'RGBA')
        a, b = art_box(normalize(tight)[0]), art_box(normalize(loose)[0])
        self.assertLess(abs((a[2] - a[0]) - (b[2] - b[0])), 4)

    def test_wide_symbol_uses_width_but_never_touches_the_edge(self):
        canvas, info = normalize(drawn((1200, 200), (0, 0, 0, 0), [('rectangle', (0, 60, 1199, 140), (10, 10, 10, 255))], 'RGBA'))
        left, top, right, bottom = art_box(canvas)
        self.assertLessEqual((right - left) / 512, LIMIT + 0.01)
        self.assertGreater(left, 10)
        self.assertIn('too_wide', info['warnings'])

    def test_colored_background_is_kept_and_flagged(self):
        canvas, info = normalize(drawn((300, 300), (200, 20, 30), [('ellipse', (80, 80, 220, 220), 'white')]))
        self.assertFalse(info['removed'])
        left, top, _, _ = art_box(canvas)
        self.assertEqual(canvas.getpixel((left + 2, top + 2))[:3], (200, 20, 30))
        self.assertIn('colored_background', info['warnings'])

    def test_keep_background_option_and_size_steps(self):
        source = drawn((400, 400), 'white', [('ellipse', (100, 100, 300, 300), (4, 116, 212))])
        kept, info = normalize(source, background='keep')
        self.assertFalse(info['removed'])
        widths = [art_box(normalize(source, size=size)[0]) for size in ('small', 'normal', 'large')]
        widths = [box[2] - box[0] for box in widths]
        self.assertLess(widths[0], widths[1])
        self.assertLess(widths[1], widths[2])

    def test_low_resolution_is_flagged(self):
        _, info = normalize(drawn((60, 60), (0, 0, 0, 0), [('ellipse', (2, 2, 57, 57), (4, 116, 212, 255))], 'RGBA'))
        self.assertIn('low_res', info['warnings'])

    def test_web_copy_is_small(self):
        data = BytesIO()
        drawn((800, 800), 'white', [('ellipse', (100, 100, 700, 700), (4, 116, 212))]).save(data, 'JPEG')
        web, printed, info = make(data.getvalue(), 'auto')
        self.assertLess(len(web), 6 * 1024)
        self.assertEqual(Image.open(BytesIO(web)).size, (96, 96))
        self.assertEqual(Image.open(BytesIO(printed)).format, 'PNG')


def upload(size=(600, 600), name='symbol.png'):
    data = BytesIO()
    drawn(size, 'white', [('ellipse', (50, 50, size[0] - 50, size[1] - 50), (4, 116, 212))]).save(data, 'PNG')
    return SimpleUploadedFile(name, data.getvalue(), content_type='image/png')


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class LogoUploadScenarios(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.manager = User.objects.create_user('logo-manager', password='LocalTestOnly!27')
        UserAccessProfile.objects.create(user=cls.manager, audience='employee')
        cls.manager.user_permissions.add(Permission.objects.get(content_type__app_label='delivery', codename='manage_delivery'))
        cls.employee = User.objects.create_user('logo-employee', password='LocalTestOnly!27')
        UserAccessProfile.objects.create(user=cls.employee, audience='employee')

    def setUp(self):
        self.enterContext(override_settings(MEDIA_ROOT=self.enterContext(TemporaryDirectory())))
        self.client.force_login(self.manager)

    def form_data(self, **changes):
        return {'official_name': '심볼 가상 기관', 'category': 'public', 'region': '', 'display_as': 'customer',
                'partner_public': 'default', 'include_in_total': 'on', 'memo': '', **changes}

    def test_new_upload_is_auto_fitted_and_options_change_the_copy(self):
        response = self.client.post('/planning/customers/new/', self.form_data(logo=upload(), logo_size='large', logo_background='remove'))
        self.assertEqual(response.status_code, 302)
        customer = Customer.objects.get()
        self.assertEqual((customer.logo_fit, customer.logo_size, customer.logo_background), ('auto', 'large', 'remove'))
        first = rendition_key(customer)
        customer.logo_size = 'small'
        self.assertNotEqual(rendition_key(customer), first)    # 크기를 바꾸면 사본을 다시 만든다

    def test_existing_logo_stays_as_is_until_auto_is_turned_on(self):
        customer = Customer.objects.create(organization=Organization.objects.create(official_name='기존 심볼 기관'),
                                           category='public', partner_public=True, logo_fit='as_is')
        customer.logo.save('old.png', upload())
        page = self.client.get(f'/planning/customers/{customer.pk}/edit/').content.decode()
        self.assertIn('새 기준으로 자동 정리', page)
        self.assertIn('data-logo-preview', page)
        data = self.form_data(official_name='기존 심볼 기관', revision=customer.updated_at.isoformat(), logo_auto='on')
        self.assertEqual(self.client.post(f'/planning/customers/{customer.pk}/edit/', data).status_code, 302)
        customer.refresh_from_db()
        self.assertEqual(customer.logo_fit, 'auto')

    def test_preview_returns_fitted_tile_and_warnings_without_saving(self):
        response = self.client.post('/planning/logos/preview/', {'logo': upload((1400, 200)), 'logo_size': 'normal', 'logo_background': 'remove'})
        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertTrue(result['image'].startswith('data:image/webp;base64,'))
        self.assertEqual(result['fit'], 'auto')
        self.assertTrue(any('가로로 너무' in text for text in result['warnings']))
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(LogoRendition.objects.count(), 0)
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(self.client.get('/planning/logos/preview/').status_code, 405)
        self.client.force_login(self.employee)
        self.assertEqual(self.client.post('/planning/logos/preview/', {'logo': upload()}).status_code, 403)
