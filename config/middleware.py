"""검색 엔진 차단(인터넷 테스트 서버, 2026-10-22 형우): 모든 응답에 noindex. 사내용이라 검색에 나오면 안 된다."""


def noindex(get_response):
    def middleware(request):
        response = get_response(request)
        response.setdefault("X-Robots-Tag", "noindex, nofollow, noarchive")
        return response
    return middleware
