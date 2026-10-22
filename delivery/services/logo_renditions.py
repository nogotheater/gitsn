"""심볼 묶음(2026-10-22 형우: '로고 뜨는 것도 오래 걸린다').

전에는 카드마다 심볼을 따로 요청했다(97번). 무료 서버(CPU 0.1개)에서는 요청마다 로그인 확인·파일 읽기를 하느라
줄을 서서 마지막 심볼이 20초 뒤에 떴다. 이제는
- 심볼마다 작은 사본(LogoRendition)을 DB에 한 번 만들어 두고(원본이 바뀌면 다시),
- 그 사람이 볼 수 있는 심볼 전부를 스타일 파일 하나(logos.css)로 묶어 한 번에 보낸다.
권한 규칙은 한 장씩 받던 logo 화면과 같다: 직원은 전부, 파트너사는 목록 표시·공개 고객사만.
"""
import base64
import hashlib
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from threading import Lock
from PIL import Image, ImageOps
from django.db import IntegrityError
from delivery.models import LogoRendition
from .current_performance import current_customers_with_any_products, current_site_presentations_with_any_products
from .logo_cache import logo_bytes

WEB_BOX = (128, 128)      # 카드 심볼은 40~48px. 화면 배율 3배 폰까지 또렷하게.
PRINT_BOX = (480, 240)    # 인쇄·PDF는 기존과 같은 크기·형식(PNG)
_MAX_FILE = 2 * 1024 * 1024
MODELS = ('customer', 'site')


def _make(data):
    """(web WebP, print PNG). 읽을 수 없는 그림이면 빈 값(카드는 글자 타일, 인쇄는 심볼 없음)."""
    if not data or len(data) > _MAX_FILE:
        return b'', b''
    try:
        with Image.open(BytesIO(data)) as original:
            if original.format not in {'PNG', 'JPEG'} or original.width * original.height > 20_000_000:
                return b'', b''
            image = ImageOps.exif_transpose(original).convert('RGBA')
        printed = image.copy()
        printed.thumbnail(PRINT_BOX, Image.Resampling.LANCZOS)
        out_print = BytesIO()
        printed.save(out_print, format='PNG')
        web = image.copy()
        web.thumbnail(WEB_BOX, Image.Resampling.LANCZOS)
        out_web = BytesIO()
        web.save(out_web, format='WEBP', quality=88, method=4)
        return out_web.getvalue(), out_print.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError):
        return b'', b''


def _read(obj):
    try:
        return logo_bytes(obj)
    except (OSError, ValueError):
        return b''


def renditions(targets, need='web'):
    """targets: [(kind, obj)] (obj.logo가 있는 것). {(kind, id 문자열): LogoRendition}. 없거나 낡은 사본은 지금 만든다.
    need: 'web' 또는 'print_png' — 다른 쪽 그림은 DB에서 읽지 않는다."""
    targets = [(kind, obj) for kind, obj in targets if obj.logo]
    found = {}
    for kind in {kind for kind, _ in targets}:
        ids = [obj.pk for k, obj in targets if k == kind]
        for row in LogoRendition.objects.filter(kind=kind, object_id__in=ids).defer('print_png' if need == 'web' else 'web'):
            found[(kind, str(row.object_id))] = row
    stale = [(kind, obj) for kind, obj in targets
             if (kind, str(obj.pk)) not in found or found[(kind, str(obj.pk))].source != obj.logo.name]
    if stale:
        # 저장소에서 원본 받기는 동시에(하나씩 받으면 97개에 20초), DB 쓰기는 여기서 차례로
        with ThreadPoolExecutor(max_workers=8) as pool:
            made = list(pool.map(lambda pair: _make(_read(pair[1])), stale))
        for (kind, obj), (web, printed) in zip(stale, made):
            try:
                row, _ = LogoRendition.objects.update_or_create(
                    kind=kind, object_id=obj.pk, defaults={'source': obj.logo.name, 'web': web, 'print_png': printed})
            except IntegrityError:   # 다른 요청이 같은 순간에 만들었다
                row = LogoRendition.objects.get(kind=kind, object_id=obj.pk)
            found[(kind, str(obj.pk))] = row
    return found


def visible_logo_targets(audience):
    """이 사람이 볼 수 있는 심볼(현재 계약이 있는 고객사·장소). 파트너사는 목록 표시·공개만(logo 화면과 같은 규칙)."""
    out = []
    for kind in MODELS:
        rows = current_customers_with_any_products(()) if kind == 'customer' else current_site_presentations_with_any_products(())
        if audience != 'employee':
            rows = rows.filter(show_in_list=True, partner_public=True)
        out += [(kind, obj) for obj in rows.exclude(logo='').only('id', 'logo', 'updated_at').order_by('pk')]
    return out


def _version(audience, targets):
    digest = hashlib.sha256(audience.encode())
    for kind, obj in targets:
        digest.update(f'|{kind}:{obj.pk}:{obj.logo.name}'.encode())
    return digest.hexdigest()[:16]


def logo_signature(audience):
    """심볼 묶음의 판 번호: 누가(직원/파트너사) 어떤 심볼 파일들을 보는지. 하나라도 바뀌면 달라진다."""
    return _version(audience, visible_logo_targets(audience))


def logo_class(object_id):
    return 'l' + str(object_id).replace('-', '')


_css_cache = {}
_css_lock = Lock()


def logo_css(audience):
    """(판 번호, 스타일 파일 내용). 같은 판이면 서버 메모리에 둔 것을 그대로 쓴다."""
    targets = visible_logo_targets(audience)
    version = _version(audience, targets)
    with _css_lock:
        if version in _css_cache:
            return version, _css_cache[version]
    rows = renditions(targets, need='web')
    lines = ['/* 납품현황 심볼 묶음(서버가 만든 파일) */']
    for kind, obj in targets:
        row = rows.get((kind, str(obj.pk)))
        web = bytes(row.web) if row else b''
        if web:
            encoded = base64.b64encode(web).decode('ascii')
            lines.append(f'.{logo_class(obj.pk)}{{background:#fff url(data:image/webp;base64,{encoded}) center/contain no-repeat!important;color:transparent!important}}')
    body = '\n'.join(lines).encode()
    with _css_lock:
        if len(_css_cache) > 8:
            _css_cache.clear()
        _css_cache[version] = body
    return version, body
