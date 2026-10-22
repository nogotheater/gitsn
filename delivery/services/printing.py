"""Authorized output projection; same document is used for print and PDF."""
import base64
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps
from django.conf import settings
from django.core.exceptions import PermissionDenied, SuspiciousFileOperation, ValidationError
from django.utils import timezone
from .list_order import item_order_key
from delivery.domain.products import product_sort_key, short_and_long
from delivery.models import Category, Customer, SitePresentation
from .access import audience_for_user
from .logo_renditions import renditions
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
    # 심볼은 미리 줄여 둔 사본(LogoRendition)에서 — 저장소에서 하나씩 받던 것이 서버가 깬 직후 25초 걸렸다(2026-10-22, 속도)
    logos, missing = {}, []
    for kind, model in [('customer', Customer), ('site', SitePresentation)]:
        ids = [item['id'] for item in items if item['kind'] == kind and item['has_logo']]
        for obj in model.objects.filter(pk__in=ids).only('id', 'logo', 'updated_at'):
            key = (kind, str(obj.pk), obj.logo.name)
            if key in _LOGO_CACHE:
                logos[key[:2]] = _LOGO_CACHE[key]
            else:
                missing.append((kind, obj))
    if missing:
        if len(_LOGO_CACHE) > 1000:
            _LOGO_CACHE.clear()
        for (kind, object_id), row in renditions(missing, need='print_png').items():
            data = bytes(row.print_png)
            value = 'data:image/png;base64,' + base64.b64encode(data).decode('ascii') if data else ''
            _LOGO_CACHE[(kind, object_id, row.source)] = value
            logos[(kind, object_id)] = value
    groups, totals = [], []
    for code, label in Category.choices:
        count = payload['counts']['by_category'][code]
        if count:
            totals.append({'label': label, 'count': count})
    # 섹션은 화면 목록과 같다: 지자체·의회는 권역별(C2, 형우 2026-10-21 '인쇄·PDF도 권역별').
    order = item_order_key(items)
    for section in list_sections(payload['counts']):
        label = section['label']
        pair = (section['code'], section['region'])
        cards = []
        for item in sorted((row for row in items if section_of(row['category'], row['region']) == pair), key=lambda row: (*order(row), row['kind'], row['id'])):
            cards.append({'name': item['name'], 'symbol': item['name'][:1],
                          'region': '',
                          'logo': logos.get((item['kind'], item['id']), '')})
        if cards:
            groups.append({'label': label, 'rows': [cards[index:index + 4] for index in range(0, len(cards), 4)]})
    title = '지슨의 보안 솔루션 도입 고객사'
    subtitle = ''
    # 제목은 제품 코드로 'Alpha-I, Alpha-S 고객사'(2026-10-22 형우). 순서는 화면 전체 제품 순서(I, S, B, D, P, H, C).
    titled = [short_and_long(p.code, p.name) for p in sorted(products, key=lambda p: product_sort_key(p.marker, p.name, p.pk))]
    if len(titled) == 1:
        title, subtitle = titled[0][0] + ' 고객사', titled[0][1]
    elif titled:
        title = ', '.join(short for short, _long in titled) + ' 고객사'
    conditions = []
    if len(products) > 1:
        conditions.append('선택 제품 중 하나 이상 도입')
    # 고른 분류는 바로 위 분류별 숫자 줄에 이미 나온다 — 조건 줄에는 다시 적지 않는다(2026-10-22 형우).
    return {'title': title, 'subtitle': subtitle, 'groups': groups, 'counts': payload['counts'],
            'category_totals': totals, 'conditions': ' · '.join(conditions),
            'scope_label': '공개 고객사 및 비공개 집계' if audience == 'partner' else dict(SCOPE_CHOICES)[scope],
            'date': timezone.localdate(), 'is_partner': audience == 'partner'}


@lru_cache(maxsize=16)
def _asset(path, mtime, encode):
    data = Path(path).read_bytes()
    return base64.b64encode(data).decode('ascii') if encode else data.decode('utf-8')


def _cached(path, encode=False):
    # 파일이 바뀌면(수정 시각) 다시 읽고, 아니면 메모리에 둔 것을 쓴다(2026-10-22, 글꼴 7MB를 매번 읽지 않게).
    return _asset(str(path), path.stat().st_mtime_ns, encode)


def document_assets():
    root = Path(settings.BASE_DIR) / 'static/delivery'
    return {'print_css': _cached(root / 'print.css'),
            'print_layout_js': _cached(root / 'print-layout.js'),
            'print_font': _cached(root / 'fonts/FreesentationVF.ttf', encode=True),
            'brand_logo': _cached(root / 'img/logo.png', encode=True)}


_LOGO_CACHE = {}


# 인쇄용 심볼 data URI를 서버 메모리에: 키는 (종류, id, 원본 파일 이름)


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
