"""로고 파일 메모리 보관(2026-10-22, 인터넷 테스트 서버 속도). 권한 확인은 지금처럼 매 요청 서버가 하고,
파일 내용만 저장소(Supabase)에서 매번 다시 받지 않게 서버 메모리에 잠깐 둔다. 브라우저 저장(no-store) 정책은 그대로."""
from collections import OrderedDict
from threading import Lock

_LIMIT_BYTES = 32 * 1024 * 1024
_MAX_FILE = 2 * 1024 * 1024 + 1
_cache = OrderedDict()
_size = 0
_lock = Lock()


def logo_bytes(obj):
    """obj.logo 파일 내용. (파일 이름, 수정 시각)이 같으면 메모리에서 꺼낸다."""
    global _size
    key = (obj.logo.name, getattr(obj, 'updated_at', None))
    with _lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    with obj.logo.open('rb') as stream:
        data = stream.read(_MAX_FILE)
    if len(data) < _MAX_FILE:
        with _lock:
            if key not in _cache:
                _cache[key] = data
                _size += len(data)
                while _size > _LIMIT_BYTES and _cache:
                    _old, dropped = _cache.popitem(last=False)
                    _size -= len(dropped)
    return data
