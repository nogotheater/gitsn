"""Confirmed whole-unit input rule, including strict rejection before integer coercion."""
import re

# PostgreSQL bigint storage capacity, not an additional business quantity limit.
POSTGRES_BIGINT_MAX = 9223372036854775807

def positive_quantity(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError("제품 수량은 1 이상의 정수여야 합니다.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        try:
            number = int(value.strip())
        except ValueError as exc:
            raise ValueError("제품 수량 형식을 확인해 주세요.") from exc
    else:
        raise ValueError("제품 수량은 1 이상의 정수여야 합니다.")
    if number < 1:
        raise ValueError("제품 수량은 1 이상의 정수여야 합니다.")
    if number > POSTGRES_BIGINT_MAX:
        raise ValueError("데이터베이스가 저장할 수 있는 정수 범위를 초과했습니다.")
    return number
