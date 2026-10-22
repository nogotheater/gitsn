from django.db import DatabaseError, connection
from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache

@require_GET
def index(request):
    return render(request, "setup.html")

@require_GET
@never_cache
def live(request):
    return JsonResponse({"status": "ok", "stage": 1})

@require_GET
@never_cache
def ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            if cursor.fetchone() != (1,):
                return JsonResponse({"status": "unavailable"}, status=503)
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})

@require_GET
def service_worker(request):
    """홈 화면 앱(PWA)용 서비스 워커는 사이트 맨 위 주소(/sw.js)에서 내려야 전체 화면을 맡을 수 있다."""
    body = (settings.BASE_DIR / "static/delivery/pwa/sw.js").read_text(encoding="utf-8")
    response = HttpResponse(body, content_type="application/javascript; charset=utf-8")
    response["Cache-Control"] = "no-cache"
    return response
