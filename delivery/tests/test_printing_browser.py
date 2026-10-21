import os
import re
from io import BytesIO
from tempfile import TemporaryDirectory
from unittest import skipUnless
from PIL import Image
from django.core.files.base import ContentFile
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from playwright.sync_api import sync_playwright, expect
from delivery.models import Customer, Organization, Product, Contract, ContractProduct, UserAccessProfile


def pdf_font_representations(data):
    """Inspect the uncompressed object dictionaries emitted by our fixed Skia.

    Variable fonts use Type3 CharProcs, not FontFile2/3. Verify that the
    referenced glyph and Unicode streams exist rather than accepting a
    Type3 label alone. This is a renderer smoke check, not a PDF parser.
    See Skia src/pdf/SkPDFFont.cpp: FontType and emit_subset_type3.
    """
    objects = {int(match[1]): match[2] for match in re.finditer(
        rb'(?ms)^(\d+)\s+0\s+obj\b(.*?)\bendobj\b', data)}

    def has_stream(identity):
        body = objects.get(int(identity), b'')
        stream = re.search(rb'\bstream\r?\n(.*?)endstream\b', body, re.S)
        return bool(stream and stream[1].strip(b'\r\n'))

    found = set()
    for body in objects.values():
        if any(has_stream(ref) for ref in re.findall(rb'/FontFile[23]\s+(\d+)\s+0\s+R\b', body)):
            found.add('font-program')
        if not re.search(rb'/Subtype\s*/Type3\b', body):
            continue
        glyphs = re.search(rb'/CharProcs\s*<<(.*?)>>', body, re.S)
        unicode = re.search(rb'/ToUnicode\s+(\d+)\s+0\s+R\b', body)
        refs = re.findall(rb'/[^\s/<>]+\s+(\d+)\s+0\s+R\b', glyphs[1]) if glyphs else []
        if refs and unicode and has_stream(unicode[1]) and all(has_stream(ref) for ref in refs):
            found.add('type3-glyphs-and-unicode')
    return found


@skipUnless(os.environ.get('GITSN_RUN_BROWSER_TESTS') == '1', 'Enable Chromium verification on PostgreSQL.')
@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class PrintingBrowserScenarios(StaticLiveServerTestCase):
    def setUp(self):
        self.enterContext(override_settings(MEDIA_ROOT=self.enterContext(TemporaryDirectory())))
        for role in ['employee', 'partner']:
            user = get_user_model().objects.create_user('print-browser-' + role, password='PrintScreenExample!87')
            UserAccessProfile.objects.create(user=user, audience=role)
        self.c = Product.objects.create(code='Alpha-C', name='불법촬영 탐지 시스템 Alpha-C', marker='C')
        for index in range(100):
            name = 'BROWSER_PRINT_PRIVATE_SENTINEL' if index == 99 else ('전남광주통합특별시 교육청 전남청사' if index == 1 else f'가상 고객사 {index:02}')
            customer = Customer.objects.create(organization=Organization.objects.create(official_name=name), category='public', partner_public=index != 99)
            if index < 2:
                stream = BytesIO()
                Image.new('RGB', (240, 60) if index == 0 else (40, 160), '#0474d4').save(stream, format='PNG')
                customer.logo.save(f'fictional-print-{index}.png', ContentFile(stream.getvalue()))
            contract = Contract.objects.create(customer=customer, contracting_party=customer.organization, is_active=True)
            ContractProduct.objects.create(contract=contract, product=self.c, quantity=1)

    def login(self, page, role):
        page.goto(self.live_server_url + '/login/')
        page.get_by_label('아이디').fill('print-browser-' + role)
        page.get_by_label('비밀번호').fill('PrintScreenExample!87')
        page.get_by_role('button', name='로그인', exact=True).click()
        page.wait_for_url('**/performance/')

    def test_employee_preview_scope_changes_mobile_and_multipage_pdf_download(self):
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page(viewport={'width': 1280, 'height': 900})
                self.login(page, 'employee')
                page.get_by_role('link', name='인쇄·PDF 미리보기', exact=True).click()
                expect(page.get_by_test_id('print-total')).to_have_text('100')
                page.get_by_label('출력할 고객사').select_option('public')
                page.get_by_role('button', name='범위 적용', exact=True).click()
                expect(page.get_by_test_id('print-total')).to_have_text('99')
                expect(page.locator('.reference-card')).to_have_count(99)
                self.assertEqual(page.locator('.product-mark').count(), 0)
                self.assertNotIn('BROWSER_PRINT_PRIVATE_SENTINEL', page.content())
                page.get_by_label('출력할 고객사').select_option('private')
                page.get_by_role('button', name='범위 적용', exact=True).click()
                expect(page.get_by_test_id('print-total')).to_have_text('1')
                expect(page.get_by_role('heading', name='BROWSER_PRINT_PRIVATE_SENTINEL')).to_be_visible()
                page.get_by_label('출력할 고객사').select_option('all')
                page.get_by_role('button', name='범위 적용', exact=True).click()
                expect(page.get_by_test_id('print-total')).to_have_text('100')
                expect(page.locator('#print-document')).to_have_attribute('data-ready', 'true')
                self.assertGreaterEqual(page.locator('.print-page').count(), 2)
                self.assertEqual(page.locator('.card-row').first.locator('.reference-card').count(), 4)
                self.assertGreater(page.locator('.category-group h2', has_text='공공기관 - 계속').count(), 0)
                self.assertEqual(page.locator('.repeat-head').count(), page.locator('.print-page').count() - 1)
                self.assertTrue(page.evaluate('''() => Array.from(document.querySelectorAll('.reference-card')).every(card => {
                    const logo = card.querySelector('.symbol').getBoundingClientRect();
                    const name = card.querySelector('h3').getBoundingClientRect();
                    const style = getComputedStyle(card.querySelector('h3'));
                    return Math.abs((logo.top + logo.bottom - name.top - name.bottom) / 2) < 1.1 &&
                        Math.abs(parseFloat(style.fontSize) - 11 * 96 / 72) < .1 && style.fontWeight === '550';
                })'''))
                self.assertTrue(page.evaluate('''() => Array.from(document.querySelectorAll('.symbol img')).every(image => {
                    const rect = image.getBoundingClientRect();
                    return Math.abs(rect.width / rect.height - image.naturalWidth / image.naturalHeight) < .03;
                })'''))
                self.assertTrue(page.evaluate('''() => Array.from(document.querySelectorAll('.page-body')).every(body => {
                    const content = body.querySelector('.page-content').getBoundingClientRect();
                    const footer = body.querySelector('.document-footer').getBoundingClientRect();
                    return content.bottom < footer.top && Array.from(body.querySelectorAll('.category-group')).every(group => group.querySelector('.card-row'));
                })'''))
                self.assertEqual(page.locator('.private-note').count(), 0)
                page.set_viewport_size({'width': 375, 'height': 812})
                page.wait_for_function('document.documentElement.scrollWidth <= window.innerWidth + 1')
                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
                page.evaluate('window.print = () => { window.printRequested = true; }')
                page.get_by_role('button', name='인쇄', exact=True).click()
                page.wait_for_function('window.printRequested === true')
                with page.expect_download(timeout=60000) as info:
                    page.get_by_role('link', name='PDF 저장', exact=True).click()
                download = info.value
                self.assertTrue(download.suggested_filename.endswith('.pdf'))
                from pathlib import Path
                data = Path(download.path()).read_bytes()
                self.assertTrue(data.startswith(b'%PDF-'))
                self.assertGreater(len(re.findall(rb'/Type\s*/Page\b', data)), 1)
                fonts = pdf_font_representations(data)
                self.assertTrue(fonts, 'No font program or Type3 glyph/Unicode streams found in the generated PDF.')
                print('STAGE5_PDF_FONT_CHECK_OK: ' + ', '.join(sorted(fonts)), flush=True)
            finally:
                browser.close()

    def test_partner_print_and_pdf_keep_counts_and_omit_private_rows(self):
        with sync_playwright() as engine:
            browser = engine.chromium.launch()
            try:
                page = browser.new_page()
                self.login(page, 'partner')
                page.get_by_role('link', name='인쇄·PDF 미리보기', exact=True).click()
                expect(page.get_by_test_id('print-total')).to_have_text('100')
                expect(page.locator('.reference-card')).to_have_count(99)
                expect(page.locator('.private-note')).to_have_text('비공개 실적 1곳 포함')
                self.assertNotIn('BROWSER_PRINT_PRIVATE_SENTINEL', page.content())
                self.assertEqual(page.locator('select[name="scope"]').count(), 0)
                result = page.request.get(self.live_server_url + '/performance/print/pdf/')
                self.assertEqual(result.status, 200)
                self.assertTrue(result.body().startswith(b'%PDF-'))
                self.assertEqual(page.request.get(self.live_server_url + '/performance/print/pdf/?scope=private').status, 403)
            finally:
                browser.close()
