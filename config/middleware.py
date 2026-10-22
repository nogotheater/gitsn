"""검색 엔진 차단(인터넷 테스트 서버, 2026-10-22 형우): 모든 응답에 noindex. 사내용이라 검색에 나오면 안 된다."""


def noindex(get_response):
    def middleware(request):
        response = get_response(request)
        response.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")
        return response
    return middleware


def server_timing(get_response):
    """서버가 화면을 만드는 데 쓴 시간을 응답 머리에 적는다(Server-Timing) — 속도 확인용(2026-10-22).
    화면 쪽에서 request.timing['이름'] = 밀리초 를 넣으면 함께 적힌다. 내용(고객 자료)은 담지 않는다."""
    from time import perf_counter

    def middleware(request):
        start = perf_counter()
        request.timing = {}
        response = get_response(request)
        parts = [f"{name};dur={value:.0f}" for name, value in request.timing.items()]
        parts.append(f"app;dur={(perf_counter() - start) * 1000:.0f}")
        response["Server-Timing"] = ", ".join(parts)
        return response
    return middleware
