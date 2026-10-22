"""Development scaffold only. No domain models or production configuration."""
from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured
from .env import load_local_env

BASE_DIR = Path(__file__).resolve().parent.parent
load_local_env(BASE_DIR / ".env")

def required(name):
    value = os.environ.get(name, "").strip()
    if not value or value == "GENERATE_WITH_BOOTSTRAP_SCRIPT":
        raise ImproperlyConfigured(f"{name} must be configured. Run scripts/bootstrap_env.py.")
    return value

def env_bool(name, default=False):
    raw = os.environ.get(name, str(default)).lower()
    if raw not in {"true", "false", "1", "0"}:
        raise ImproperlyConfigured(f"{name} must be true/false or 1/0.")
    return raw in {"true", "1"}

SECRET_KEY = required("DJANGO_SECRET_KEY")
# 40자 이상(Render가 만들어 주는 256비트 base64 값이 44자, 2026-10-22). PC는 bootstrap_env.py가 86자를 만든다.
if len(SECRET_KEY) < 40:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must contain at least 40 characters.")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = [x.strip() for x in required("DJANGO_ALLOWED_HOSTS").split(",") if x.strip()]
if "*" in ALLOWED_HOSTS:
    raise ImproperlyConfigured("Wildcard ALLOWED_HOSTS is not supported by this scaffold.")

INSTALLED_APPS = [
    "django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
    "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles",
    "delivery.apps.DeliveryConfig",
]
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "config.middleware.noindex",
]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
        "delivery.context_processors.navigation",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": required("POSTGRES_DB"),
    "USER": required("POSTGRES_USER"),
    "PASSWORD": required("POSTGRES_PASSWORD"),
    "HOST": required("POSTGRES_HOST"),
    "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    "CONN_MAX_AGE": 0,
    "OPTIONS": {"connect_timeout": int(os.environ.get("POSTGRES_CONNECT_TIMEOUT", "5"))},
}}
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/performance/"
LOGOUT_REDIRECT_URL = "/login/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True

# 인터넷 테스트 서버(Render + Supabase, 2026-10-22 형우). 아래 값은 서버 환경에서만 켜진다 — PC 실행에는 영향 없음.
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()   # Render가 자동으로 넣어 주는 주소(○○.onrender.com)
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append("https://" + _render_host)
if env_bool("DJANGO_BEHIND_PROXY", False):   # 앞단(Render)이 https를 맡는다
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if env_bool("DJANGO_SERVE_STATIC", False):   # 정적 파일(CSS·JS·아이콘)은 WhiteNoise가 낸다
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
# 인터넷 서버에서는 DB 연결을 60초 재사용(요청마다 암호화 연결을 새로 맺으면 느리다, 2026-10-22). PC는 지금처럼 0.
DATABASES["default"]["CONN_MAX_AGE"] = int(os.environ.get("POSTGRES_CONN_MAX_AGE", "60" if _render_host else "0"))
DATABASES["default"]["CONN_HEALTH_CHECKS"] = DATABASES["default"]["CONN_MAX_AGE"] > 0
if os.environ.get("POSTGRES_SSLMODE", "").strip():   # Supabase는 암호화 연결만 받는다
    DATABASES["default"]["OPTIONS"]["sslmode"] = os.environ["POSTGRES_SSLMODE"].strip()
if os.environ.get("MEDIA_S3_BUCKET", "").strip():
    # 로고 파일은 Supabase 저장소(S3 방식, 비공개 버킷)에 둔다. 화면에는 지금처럼 로그인한 사람에게만 서버가 내려준다.
    STORAGES = {
        "default": {"BACKEND": "storages.backends.s3.S3Storage", "OPTIONS": {
            "bucket_name": required("MEDIA_S3_BUCKET"),
            "endpoint_url": required("MEDIA_S3_ENDPOINT"),
            "access_key": required("MEDIA_S3_ACCESS_KEY"),
            "secret_key": required("MEDIA_S3_SECRET_KEY"),
            "region_name": os.environ.get("MEDIA_S3_REGION", "ap-southeast-1"),
            "addressing_style": "path",
            "signature_version": "s3v4",
            "default_acl": None,
            "querystring_auth": True,
            "file_overwrite": False,
        }},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
