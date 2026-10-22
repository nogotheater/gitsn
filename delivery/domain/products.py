"""제품 표시 순서(2026-10-22 형우): 마킹·필터 칩·제품 목록 어디서나 I, S, B, D, P, H, C.

이 순서에 없는 기호는 맨 뒤로, 같은 자리 안에서는 제품명 순이다.
"""
PRODUCT_ORDER = ('I', 'S', 'B', 'D', 'P', 'H', 'C')
_RANK = {marker: index for index, marker in enumerate(PRODUCT_ORDER)}


def marker_rank(marker):
    return _RANK.get((marker or '').strip().upper(), len(PRODUCT_ORDER))


def product_sort_key(marker, name='', pk=''):
    return (marker_rank(marker), (name or '').casefold(), str(pk))


def short_and_long(code, name):
    """제품을 부르는 짧은 이름(Alpha-I 같은 모델명)과 긴 설명을 나눈다.

    제품 관리의 '제품 코드'·'제품명' 중 어느 칸에 모델명을 넣었는지와 상관없이, 짧은 쪽을 모델명으로 본다
    (2026-10-22: 실제 자료는 제품명에 Alpha-I, 제품 코드에 긴 설명이 들어 있음).
    """
    code, name = (code or '').strip(), (name or '').strip()
    if not code or not name:
        return code or name, ''
    short, long = (code, name) if len(code) <= len(name) else (name, code)
    long = long.removesuffix(short).strip()
    return short, ('' if long == short else long)


def ordered_products(queryset):
    """제품 쿼리셋을 표시 순서로(폼 선택지·관리 목록용)."""
    from django.db.models import Case, IntegerField, Value, When
    rank = Case(*[When(marker__iexact=marker, then=Value(index)) for index, marker in enumerate(PRODUCT_ORDER)],
                default=Value(len(PRODUCT_ORDER)), output_field=IntegerField())
    return queryset.annotate(display_rank=rank).order_by('display_rank', 'name', 'pk')
