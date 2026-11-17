"""새로 올리는 심볼을 지금 등록된 심볼들과 같은 모양으로 맞춘다(2026-11-17 형우: 팀원이 올려도 통일감 있게).

기준은 2026-11-17에 잰 기존 심볼 104개의 가운데값이다: 정사각 칸에 그림이 약 77%(좌우 여백 12%, 위아래 17%),
투명 배경. 순서:
1. 배경 찾기: 가장자리가 투명하면 투명, 아니면 가장자리 대부분이 한 색이면 그 색.
2. 흰(밝은) 배경은 가장자리에서 이어진 부분만 투명하게 지운다(로고 안의 흰 부분은 남긴다). 색 배경은 로고의 일부로 둔다.
3. 그림만 남게 여백을 잘라낸다.
4. 면적 기준으로 크기를 정한다: 정사각 로고는 칸의 77%, 가로로 긴 로고는 너비를 더 쓰되(최대 90%) 납작해진다.
5. 정사각 투명 캔버스 가운데에 놓는다.
손으로 고치는 값은 크기(작게·보통·크게)와 배경(지우기·유지) 두 가지뿐이다. numpy 없이 Pillow만 쓴다.
올리는 파일은 기관 이름 글자 없이 심볼만 있는 것이다(2026-11-17 형우: '우리가 심볼 형태로만 업로드'). 글자를 잘라내지 않는다.
"""
from PIL import Image, ImageChops, ImageDraw, ImageOps

TARGET = 0.77           # 정사각 로고가 차지하는 칸의 비율(기존 심볼 가운데값)
LIMIT = 0.90            # 어떤 로고도 이보다 넓거나 높게 놓지 않는다(여백 최소 5%)
SIZE_FACTOR = {'small': 0.88, 'normal': 1.0, 'large': 1.12}
LIGHT = 232             # 이보다 밝은 배경색이면 '흰 배경'으로 보고 지운다
TOLERANCE = 18          # 배경색과 이만큼 가까우면 배경
SOFT = 40               # 경계 부드럽게(배경과 거리가 TOLERANCE~TOLERANCE+SOFT 사이면 반투명)
LOW_RES = 120           # 그림(여백 뺀 부분)의 긴 변이 이보다 작으면 '해상도 낮음'
HEAVY = 0.82            # 그림 상자를 이 비율 넘게 꽉 채운 로고(꽉 찬 네모)는 같은 면적이어도 커 보여서 조금 줄인다(원은 약 0.79라 그대로)


def _border_points(width, height, step):
    for x in range(0, width, step):
        yield x, 0
        yield x, height - 1
    for y in range(0, height, step):
        yield 0, y
        yield width - 1, y


def detect_background(image):
    """('transparent', None) | ('solid', (r, g, b)) | ('none', None)."""
    width, height = image.size
    step = max(1, min(width, height) // 64)
    points = list(_border_points(width, height, step))
    pixels = [image.getpixel(p) for p in points]
    if sum(1 for p in pixels if p[3] < 16) >= len(pixels) * 0.5:
        return 'transparent', None
    opaque = [p[:3] for p in pixels if p[3] >= 200]
    if not opaque:
        return 'none', None
    # 가장 흔한 색(조금씩 다른 값은 같은 색으로 묶는다)
    buckets = {}
    for rgb in opaque:
        key = tuple(v // 8 for v in rgb)
        buckets.setdefault(key, []).append(rgb)
    best = max(buckets.values(), key=len)
    if len(best) < len(pixels) * 0.6:
        return 'none', None
    color = tuple(sum(c[i] for c in best) // len(best) for i in range(3))
    return 'solid', color


def remove_background(image, color):
    """가장자리에서 이어진 배경색 영역만 투명하게. 경계는 거리만큼 반투명."""
    rgb = image.convert('RGB')
    distance = ImageChops.difference(rgb, Image.new('RGB', rgb.size, color))
    r, g, b = distance.split()
    distance = ImageChops.lighter(ImageChops.lighter(r, g), b)            # 채널 중 가장 큰 차이
    near = distance.point(lambda d: 255 if d <= TOLERANCE + SOFT else 0)  # 배경 또는 경계 후보
    region = near.copy()
    width, height = region.size
    for point in _border_points(width, height, max(1, min(width, height) // 128)):
        if region.getpixel(point) == 255:
            ImageDraw.floodfill(region, point, 128)
    connected = region.point(lambda v: 255 if v == 128 else 0)           # 가장자리에서 이어진 부분만
    ramp = distance.point(lambda d: 0 if d <= TOLERANCE else (255 if d >= TOLERANCE + SOFT else int((d - TOLERANCE) * 255 / SOFT)))
    new_alpha = ImageChops.multiply(image.getchannel('A'), ramp)
    alpha = Image.composite(new_alpha, image.getchannel('A'), connected)
    out = image.copy()
    out.putalpha(alpha)
    return out


def normalize(source, *, size='normal', background='remove', canvas=512):
    """source: 열린 Pillow 이미지. (정사각 RGBA 캔버스, 정보 dict)."""
    image = ImageOps.exif_transpose(source).convert('RGBA')
    kind, color = detect_background(image)
    removed = False
    if kind == 'solid' and background == 'remove' and min(color) >= LIGHT:
        image = remove_background(image, color)
        removed = True
    if kind == 'solid' and not removed and min(color) < LIGHT:
        # 색 배경(파란 네모 안의 흰 마크 등): 그 네모가 심볼이다 → 통째로 쓴다
        box = (0, 0) + image.size
    elif kind == 'solid' and not removed:
        # 흰 배경 '유지': 배경은 남기고 바깥의 흰 여백만 잘라낸다
        diff = ImageChops.difference(image.convert('RGB'), Image.new('RGB', image.size, color))
        r, g, b = diff.split()
        box = ImageChops.lighter(ImageChops.lighter(r, g), b).point(lambda d: 255 if d > TOLERANCE else 0).getbbox()
    else:
        box = image.getchannel('A').point(lambda a: 255 if a > 8 else 0).getbbox()
    if not box:
        # 지우고 나니 아무것도 안 남는 그림(통째로 흰 그림 등)은 사라지게 두지 않고 올린 그대로 쓴다
        image = ImageOps.exif_transpose(source).convert('RGBA')
        removed = False
        box = (0, 0) + image.size
    art = image.crop(box)
    width, height = art.size
    aspect = width / height
    factor = SIZE_FACTOR.get(size, 1.0)
    if kind == 'solid' and not removed:
        coverage = 1.0   # 색 배경째로 쓰는 로고는 상자가 꽉 찬 셈
    else:
        histogram = art.getchannel('A').histogram()
        coverage = sum(i * n for i, n in enumerate(histogram)) / (255 * width * height)
    if coverage > HEAVY:
        factor *= (HEAVY / coverage) ** 0.5    # 꽉 찬 네모일수록 조금(최대 약 10%) 작게
    limit = min(0.96, LIMIT * (factor if factor > 1 else 1))
    area = (TARGET * factor) ** 2
    h = (area / aspect) ** 0.5
    w = h * aspect
    if w > limit:
        w, h = limit, limit / aspect
    if h > limit:
        h, w = limit, limit * aspect
    target = (max(1, round(w * canvas)), max(1, round(h * canvas)))
    art = art.resize(target, Image.Resampling.LANCZOS)
    out = Image.new('RGBA', (canvas, canvas), (0, 0, 0, 0))
    out.paste(art, ((canvas - target[0]) // 2, (canvas - target[1]) // 2), art)
    warnings = []
    if max(width, height) < LOW_RES:
        warnings.append('low_res')
    if aspect > 4:
        warnings.append('too_wide')
    if aspect < 0.4:
        warnings.append('too_tall')
    if kind == 'solid' and not removed and background == 'remove':
        warnings.append('colored_background')
    return out, {'background': kind, 'removed': removed, 'art_px': (width, height), 'aspect': round(aspect, 2),
                 'coverage': round(coverage, 2),
                 'warnings': warnings}
