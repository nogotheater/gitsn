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
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must contain at least 50 characters.")
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
