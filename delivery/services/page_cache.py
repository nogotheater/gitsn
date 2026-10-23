"""납품현황 화면 재료를 서버 메모리에 잠깐 둔다(2026-10-23, 속도 4번).

무료 서버(CPU 0.1개)는 504곳 화면을 만들 때마다 1~1.5초 걸렸다. 자료가 그대로면 만들어 둔 재료를 다시 쓴다.
- 판 번호(data_signature): 화면에 나오는 표마다 (마지막 수정 시각, 줄 수)를 한 번의 질의로 읽는다.
  고객사·기관·장소·제품·계약·계약 제품·설치 장소 연결 등이 고쳐지거나 지워지면 달라진다.
- 혹시 판 번호가 못 잡는 변경이 있어도 10분이 지나면 새로 만든다.
- 사람마다 다른 것(로그인 이름, 보안 토큰)은 넣지 않는다. 열쇠에 직원/파트너사 구분과 조건(제품·분류·검색어)이 들어간다.
- 인터넷 서버(RENDER_EXTERNAL_HOSTNAME)에서만 켠다. PC·검사는 PERFORMANCE_PAGE_CACHE 설정으로 켤 수 있다.
"""
import os
from collections import OrderedDict
from threading import Lock
from time import monotonic
from django.conf import settings
from django.db import connection

TTL_SECONDS = 600
_LIMIT = 24
_store = OrderedDict()
_lock = Lock()


def enabled():
    value = getattr(settings, 'PERFORMANCE_PAGE_CACHE', None)
    if value is None:
        return bool(os.environ.get('RENDER_EXTERNAL_HOSTNAME'))
    return bool(value)


def _tables():
    from delivery.models import (Contract, ContractProduct, ContractSite, Customer, InstallationSite,
                                 Organization, Product, SitePresentation, SiteProductSelection)
    return [model._meta.db_table for model in (Customer, Organization, InstallationSite, SitePresentation, Product,
                                                Contract, ContractProduct, ContractSite, SiteProductSelection)]


def data_signature():
    parts = ', '.join(f'(SELECT concat(max(updated_at), \'/\', count(*)) FROM {connection.ops.quote_name(table)})'
                      for table in _tables())
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT {parts}')
        return tuple(cursor.fetchone())


def get(key):
    if key is None:
        return None
    with _lock:
        hit = _store.get(key)
        if hit is None:
            return None
        made, value = hit
        if monotonic() - made > TTL_SECONDS:
            del _store[key]
            return None
        _store.move_to_end(key)
        return value


def put(key, value):
    if key is None:
        return
    with _lock:
        _store[key] = (monotonic(), value)
        _store.move_to_end(key)
        while len(_store) > _LIMIT:
            _store.popitem(last=False)


def clear():
    with _lock:
        _store.clear()
