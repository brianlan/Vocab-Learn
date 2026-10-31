import os
import math
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent
DEBUG = os.getenv("DJANGO_DEBUG", "1") == "1"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "development-only-change-before-deployment")
if not DEBUG and SECRET_KEY == "development-only-change-before-deployment":
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY for deployment.")
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]").split(",")
CSRF_TRUSTED_ORIGINS = [x for x in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if x]
INSTALLED_APPS = ["django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes",
                  "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "learning"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "whitenoise.middleware.WhiteNoiseMiddleware",
              "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware",
              "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware",
              "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware",
              "learning.middleware.PrivatePages"]
ROOT_URLCONF = "vocab.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"],
              "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.request",
              "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "vocab.wsgi.application"
DATA_DIR = Path(os.getenv("APP_DATA_DIR", str(BASE_DIR / "var")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR = Path(os.getenv("AUDIO_DIR", str(DATA_DIR / "audio")))
AUDIO_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": os.getenv("DATABASE_PATH", str(DATA_DIR / "db.sqlite3")),
    "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"},
    "TEST": {"NAME": str(DATA_DIR / "test.sqlite3")}}}
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
                            {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}]
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("DISPLAY_TIMEZONE", "Asia/Shanghai")
USE_TZ = True
USE_I18N = False
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage" if DEBUG else "whitenoise.storage.CompressedManifestStaticFilesStorage"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
if os.getenv("TRUST_PROXY", "0") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = not DEBUG
SECURE_REDIRECT_EXEMPT = [r"^health/$"]
SECURE_HSTS_SECONDS = 3600 if not DEBUG else 0
# A private home.arpa hostname is not submitted to a public preload list or extended to other subdomains.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]
X_FRAME_OPTIONS = "DENY"
DATA_UPLOAD_MAX_MEMORY_SIZE = 52 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 256 * 1024
def positive_budget(name, default):
    try:
        value = float(os.getenv(name, str(default)))
        if value <= 0 or not math.isfinite(value):
            raise ValueError
        return value
    except ValueError:
        raise ImproperlyConfigured(name+" must be a positive finite number.") from None

ASSESSMENT_TIMEOUT_SECONDS = positive_budget("ASSESSMENT_TIMEOUT_SECONDS", 300)
GENERATION_TIMEOUT_SECONDS = positive_budget("GENERATION_TIMEOUT_SECONDS", 300)
WORKER_CLEANUP_GRACE_SECONDS = positive_budget("WORKER_CLEANUP_GRACE_SECONDS", 10)
try:
    WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "2"))
except ValueError:
    raise ImproperlyConfigured("WORKER_CONCURRENCY must be a whole number between 1 and 16.") from None
if not 1 <= WORKER_CONCURRENCY <= 16:
    raise ImproperlyConfigured("WORKER_CONCURRENCY must be between 1 and 16.")
