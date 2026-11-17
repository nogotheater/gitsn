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
from .logo_normalize import normalize

WEB_SIZE = 96            # 카드 심볼은 40~48px → 2배면 충분(2026-11-17, 용량: 128px·q88 → 96px·q80, 약 4.3KB → 2.5KB)
PRINT_BOX = (480, 240)    # 인쇄·PDF(올린 그대로인 심볼): 기존과 같은 크기·형식(PNG)
PRINT_CANVAS = 360        # 인쇄·PDF(자동 정리한 심볼): 정사각 PNG
RULE = 'r2'               # 사본 만드는 규칙이 바뀌면 올려서 모든 사본을 다시 만든다
_MAX_FILE = 2 * 1024 * 1024
MODELS = ('customer', 'site')
FIELDS = ('id', 'logo', 'updated_at', 'logo_fit', 'logo_size', 'logo_background')


def rendition_key(obj):
    """사본이 무엇으로 만들어졌는지: 원본 파일 + 정리 방식 + 크기 + 배경 + 규칙 판. 하나라도 바뀌면 다시 만든다."""
    return '|'.join([obj.logo.name, getattr(obj, 'logo_fit', 'as_is'), getattr(obj, 'logo_size', 'normal'),
                     getattr(obj, 'logo_background', 'remove'), RULE])


def _webp(image):
    """작은 WebP(q80). method=4: 6보다 100배 빠르고 크기는 2%만 크다(2026-11-17 측정: 104개 다시 만들기가 무료 서버에서 142초 걸렸다)."""
    out = BytesIO()
    image.save(out, format='WEBP', quality=80, method=4)
    return out.getvalue()


def open_logo(data):
    """올린 파일 → Pillow 이미지(PNG·JPG만, 2MB·2천만 화소 이하). 못 읽으면 None."""
    if not data or len(data) > _MAX_FILE:
        return None
    try:
        image = Image.open(BytesIO(data))
        if image.format not in {'PNG', 'JPEG'} or image.width * image.height > 20_000_000:
            return None
        image.load()
        return image
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def make(data, fit='as_is', size='normal', background='remove', need_print=True):
    """(web WebP, print PNG, info). 읽을 수 없는 그림이면 빈 값(카드는 글자 타일, 인쇄는 심볼 없음)."""
    original = open_logo(data)
    if original is None:
        return b'', b'', {'warnings': ['unreadable']}
    try:
        if fit == 'auto':
            canvas, info = normalize(original, size=size, background=background)
            if canvas is None:
                return b'', b'', {'warnings': ['empty']}
            web = canvas.resize((WEB_SIZE, WEB_SIZE), Image.Resampling.LANCZOS)
            printed = canvas.resize((PRINT_CANVAS, PRINT_CANVAS), Image.Resampling.LANCZOS)
        else:
            image = ImageOps.exif_transpose(original).convert('RGBA')
            printed = image.copy()
            printed.thumbnail(PRINT_BOX, Image.Resampling.LANCZOS)
            web = image.copy()
            web.thumbnail((WEB_SIZE, WEB_SIZE), Image.Resampling.LANCZOS)
            info = {'warnings': []}
        out_print = BytesIO()
        if need_print:
            printed.save(out_print, format='PNG')
        return _webp(web), out_print.getvalue(), info
    except (OSError, ValueError, Image.DecompressionBombError):
        return b'', b'', {'warnings': ['unreadable']}


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
             if (kind, str(obj.pk)) not in found or found[(kind, str(obj.pk))].source != rendition_key(obj)]
    if stale:
        # 저장소에서 원본 받기는 동시에(하나씩 받으면 97개에 20초), DB 쓰기는 여기서 차례로
        with ThreadPoolExecutor(max_workers=8) as pool:
            made = list(pool.map(lambda pair: make(_read(pair[1]), getattr(pair[1], 'logo_fit', 'as_is'),
                                                   getattr(pair[1], 'logo_size', 'normal'), getattr(pair[1], 'logo_background', 'remove')), stale))
        for (kind, obj), (web, printed, info) in zip(stale, made):
            try:
                row, _ = LogoRendition.objects.update_or_create(
                    kind=kind, object_id=obj.pk, defaults={'source': rendition_key(obj), 'web': web, 'print_png': printed, 'info': info})
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
        out += [(kind, obj) for obj in rows.exclude(logo='').only(*FIELDS).order_by('pk')]
    return out


def _version(audience, targets):
    digest = hashlib.sha256(audience.encode())
    for kind, obj in targets:
        digest.update(f'|{kind}:{obj.pk}:{rendition_key(obj)}'.encode())
    return digest.hexdigest()[:16]


def logo_signature(audience):
    """심볼 묶음의 판 번호: 누가(직원/파트너사) 어떤 심볼 파일들을 보는지. 하나라도 바뀌면 달라진다."""
    return _version(audience, visible_logo_targets(audience))


def logo_bundle(audience):
    """(판 번호, 묶음에 든 심볼 {(kind, id)}) — 고객사 관리도 납품현황과 같은 묶음을 쓴다(2026-11-17 형우: 로고 크기가 다르다, 느리다)."""
    targets = visible_logo_targets(audience)
    return _version(audience, targets), {(kind, str(obj.pk)) for kind, obj in targets}


def rendition_version(obj):
    """묶음에 없는 심볼 한 장의 주소 판 번호. 심볼이나 정리 방식이 바뀌면 주소가 바뀐다."""
    return hashlib.sha256(rendition_key(obj).encode()).hexdigest()[:12]


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


def logo_fallbacks(items, audience):
    """심볼이 없는 카드가 대신 쓸 심볼(2026-11-17 형우: '영천시 로고를 올렸는데 영천시 환경사업소에는 반영이 안 됐다' → 자동으로).

    - 고객사: 계약 당사자가 다른 기관이고 그 기관이 심볼 있는 고객사이면 그 심볼(예: 영천시 환경사업소 → 영천시).
    - 설치 장소: 그 장소가 연결된 계약의 고객사 심볼.
    유효 계약 중 가장 최근 것을 따른다. 파트너사에게는 목록 표시·공개 고객사의 심볼만 빌려 준다(심볼 묶음과 같은 규칙).
    돌려주는 것: {(종류, id 문자열): 심볼을 빌려 줄 고객사 id 문자열}.
    """
    from django.db.models import F
    from delivery.models import Contract, ContractSite
    missing_customers = [item['id'] for item in items if item['kind'] == 'customer' and not item['has_logo']]
    missing_sites = [item['id'] for item in items if item['kind'] == 'site' and not item['has_logo']]
    out = {}
    allowed = {} if audience == 'employee' else {'show_in_list': True, 'partner_public': True}
    if missing_customers:
        rows = (Contract.objects.filter(customer_id__in=missing_customers, is_active=True, contracting_party__customer__isnull=False)
                .exclude(contracting_party__customer__logo='').exclude(contracting_party__customer__id=F('customer_id'))
                .filter(**{f'contracting_party__customer__{key}': value for key, value in allowed.items()})
                .order_by('-created_at').values_list('customer_id', 'contracting_party__customer__id'))
        for target, source in rows:
            out.setdefault(('customer', str(target)), str(source))
    if missing_sites:
        rows = (ContractSite.objects.filter(site__presentation__id__in=missing_sites, contract__is_active=True)
                .exclude(contract__customer__logo='')
                .filter(**{f'contract__customer__{key}': value for key, value in allowed.items()})
                .order_by('-contract__created_at').values_list('site__presentation__id', 'contract__customer_id'))
        for target, source in rows:
            out.setdefault(('site', str(target)), str(source))
    return out
