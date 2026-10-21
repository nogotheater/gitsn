"""Authorized output projection; same document is used for print and PDF."""
import base64
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps
from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousFileOperation, ValidationError
from django.utils import timezone
from delivery.models import Category, Customer, SitePresentation
from .access import audience_for_user
from .audience_performance import current_performance_payload
from .sections import section_of, sections as list_sections

SCOPE_CHOICES = [('public', '공개 고객사만'), ('private', '비공개 고객사만'), ('all', '공개·비공개 모두')]


def logo_data(field):
    if not field:
        return ''
    try:
        with field.open('rb') as stream:
            data = stream.read(2 * 1024 * 1024 + 1)
        if len(data) > 2 * 1024 * 1024:
            return ''
        with Image.open(BytesIO(data)) as original:
            if original.format not in {'PNG', 'JPEG'}:
                return ''
            if original.width * original.height > 20_000_000:
                return ''
            image = ImageOps.exif_transpose(original)
            image.thumbnail((480, 240), Image.Resampling.LANCZOS)
            image = image.convert('RGBA')
            out = BytesIO()
            image.save(out, format='PNG')
        return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode('ascii')
    except (OSError, ValueError, SuspiciousFileOperation, Image.DecompressionBombError):
        return ''


def print_document(user, cleaned, scope):
    audience = audience_for_user(user)
    if scope not in {'all', 'public', 'private'}:
        raise ValidationError('출력할 공개 범위를 선택해 주세요.')
    if audience == 'partner' and scope != 'all':
        raise PermissionDenied('Partner output scope is fixed.')
    products = list(cleaned['products'])
    categories = list(cleaned['category'])
    payload = current_performance_payload(user, selected_product_ids=[p.pk for p in products],
               categories=categories, visibility=scope, include_badges=False)
    items = payload['items']
    # Query logo files only for the already authorized, filtered visible items.
    logos = {}
    for kind, model in [('customer', Customer), ('site', SitePresentation)]:
        ids = [item['id'] for item in items if item['kind'] == kind and item['has_logo']]
        for obj in model.objects.filter(pk__in=ids).only('id', 'logo'):
            logos[(kind, str(obj.pk))] = logo_data(obj.logo)
    groups, totals = [], []
    for code, label in Category.choices:
        count = payload['counts']['by_category'][code]
        if count:
            totals.append({'label': label, 'count': count})
    # 섹션은 화면 목록과 같다: 지자체·의회는 권역별(C2, 형우 2026-10-21 '인쇄·PDF도 권역별').
    for section in list_sections(payload['counts']):
        label = section['label']
        pair = (section['code'], section['region'])
        cards = []
        for item in sorted((row for row in items if section_of(row['category'], row['region']) == pair), key=lambda row: (row['name'].casefold(), row['kind'], row['id'])):
            cards.append({'name': item['name'], 'symbol': item['name'][:1],
                          'region': '',
                          'logo': logos.get((item['kind'], item['id']), '')})
        if cards:
            groups.append({'label': label, 'rows': [cards[index:index + 4] for index in range(0, len(cards), 4)]})
    title = '지슨의 보안 솔루션 도입 고객사'
    subtitle = ''
    if len(products) == 1:
        title = products[0].code + ' 도입 고객사'
        subtitle = products[0].name.removesuffix(products[0].code).strip()
    elif products:
        title = ', '.join(p.code for p in products) + ' 도입 고객사'
    conditions = []
    if len(products) > 1:
        conditions.append('선택 제품 중 하나 이상 도입')
    if categories:
        conditions.append(', '.join(Category(code).label for code in categories))
    return {'title': title, 'subtitle': subtitle, 'groups': groups, 'counts': payload['counts'],
            'category_totals': totals, 'conditions': ' · '.join(conditions),
            'scope_label': '공개 고객사 및 비공개 집계' if audience == 'partner' else dict(SCOPE_CHOICES)[scope],
            'date': timezone.localdate(), 'is_partner': audience == 'partner'}


def document_assets():
    root = Path(settings.BASE_DIR) / 'static/delivery'
    return {'print_css': (root / 'print.css').read_text(),
            'print_layout_js': (root / 'print-layout.js').read_text(),
            'print_font': base64.b64encode((root / 'fonts/FreesentationVF.ttf').read_bytes()).decode('ascii'),
            'brand_logo': base64.b64encode((root / 'img/logo.png').read_bytes()).decode('ascii')}


def render_pdf(html):
    # No user-supplied URL, cookies, local files or network request is opened.
    from playwright.sync_api import sync_playwright
    with sync_playwright() as engine:
        browser = engine.chromium.launch(timeout=20000)
        try:
            page = browser.new_page()
            page.route('**/*', lambda route: route.abort())
            page.emulate_media(media='print')
            page.set_content(html, wait_until='load', timeout=15000)
            page.add_script_tag(content=(Path(settings.BASE_DIR) / 'static/delivery/print-layout.js').read_text())
            page.evaluate('() => window.GitsnPrint.prepare()')
            return page.pdf(print_background=True, prefer_css_page_size=True, display_header_footer=False)
        finally:
            browser.close()
