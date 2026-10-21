"""지역 현황 지도(8단계)의 판정 규칙. DB를 쓰지 않는다.

제품군 묶음은 spec v3 확정 규칙을 따른다.
- 도청 보안: Alpha-I(I) · Alpha-S(S) · Alpha-B(B) · Smart-D(D) · Alpha-P(P)
- 불법촬영 보안: Alpha-C(C)
- 묶음 밖 제품(Alpha-H 등)만 있는 기관은 두 제품군 모두 미도입이다.
"""
EAVESDROP = 'eavesdrop'
CAMERA = 'camera'
FAMILIES = (
    (EAVESDROP, '도청 보안', ('I', 'S', 'B', 'D', 'P')),
    (CAMERA, '불법촬영 보안', ('C',)),
)
FAMILY_LABEL = {key: label for key, label, _m in FAMILIES}
MARKER_ORDER = ('I', 'S', 'B', 'D', 'P', 'C')


def family_of_marker(marker):
    """제품 표시 기호 → 제품군 키. 묶음 밖이면 None."""
    for key, _label, markers in FAMILIES:
        if marker in markers:
            return key
    return None
