import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from corsheaders.defaults import default_headers
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _csv(name: str) -> list:
    """A comma-separated environment variable as a list."""
    return [item.strip() for item in os.environ.get(name, "").split(",") if item.strip()]


# Local development defaults. A real deployment sets DJANGO_SECRET_KEY and DJANGO_DEBUG=0.
_DEV_SECRET_KEY = "dev-only-insecure-key-change-me"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", _DEV_SECRET_KEY)
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
if not DEBUG and SECRET_KEY == _DEV_SECRET_KEY:
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY when DJANGO_DEBUG=0.")

ALLOWED_HOSTS = ["localhost", "127.0.0.1", ".vercel.app", *_csv("DJANGO_ALLOWED_HOSTS")]
CSRF_TRUSTED_ORIGINS = ["https://*.vercel.app", *_csv("DJANGO_CSRF_TRUSTED_ORIGINS")]

if not DEBUG:
    # Behind Vercel's proxy: trust its forwarded protocol and keep cookies https-only.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# DEMO MODE: no real SMS gateway exists, so a public demo would strand visitors
# at the one-time-code step. When AUVERIA_DEMO_MODE=1, the API also returns the
# code in its response so the app can display it. NEVER enable this for real users.
DEMO_MODE = os.environ.get("AUVERIA_DEMO_MODE", "0") == "1"

# --- Auveria Bank branding / banking config (change here, nowhere else) ---
AUVERIA_BANK_NAME = "Auveria Bank"
# Placeholder 3-digit bank code for NUBAN generation. Make sure it doesn't
# clash with a real CBN bank code before you show this publicly.
AUVERIA_BANK_CODE = "777"

# --- KYC ---
KYC_PROVIDER = "apps.kyc.providers.MockIdentityProvider"
# Limits in kobo; None = no cap. Tier 1 figures (N50,000 daily / N300,000 max
# balance) come from industry write-ups. Tier 2 and 3 values are PLACEHOLDERS:
# verify all of them against the current CBN circulars before publishing.
KYC_TIERS = {
    1: {"name": "Basic", "daily_limit_kobo": 5_000_000, "max_balance_kobo": 30_000_000},
    2: {"name": "Standard", "daily_limit_kobo": 50_000_000, "max_balance_kobo": 500_000_000},
    3: {"name": "Enhanced", "daily_limit_kobo": None, "max_balance_kobo": None},
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "apps.kyc",
    "apps.accounts",
    "apps.ledger",
    "apps.security",
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "auveria.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "auveria.wsgi.application"

# Database, in order of precedence:
#   1. DATABASE_URL (hosted PostgreSQL such as Neon, used on Vercel)
#   2. DB_NAME (+ DB_USER, DB_PASSWORD, DB_HOST, DB_PORT) for a local PostgreSQL
#   3. SQLite for quick local development
# Row locking and the concurrency tests need PostgreSQL.
_database_url = os.environ.get("DATABASE_URL")
if _database_url:
    _u = urlparse(_database_url)
    _local = _u.hostname in ("localhost", "127.0.0.1")
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": _u.path.lstrip("/"),
            "USER": unquote(_u.username or ""),
            "PASSWORD": unquote(_u.password or ""),
            "HOST": _u.hostname,
            "PORT": str(_u.port or 5432),
            "OPTIONS": {
                "sslmode": parse_qs(_u.query).get("sslmode", ["disable" if _local else "require"])[0],
                "connect_timeout": 10,
            },
            # Serverless: every invocation opens its own connection, and poolers
            # (PgBouncer in transaction mode) don't support server-side cursors.
            "CONN_MAX_AGE": 0,
            "DISABLE_SERVER_SIDE_CURSORS": True,
        }
    }
elif os.environ.get("DB_NAME"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ["DB_NAME"],
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
            # Fail fast with an error instead of hanging if PostgreSQL is unreachable.
            "OPTIONS": {"connect_timeout": 5},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"  # kept (empty) so WhiteNoise has a directory to look at
# WhiteNoise serves the admin's CSS and JS straight from the installed packages,
# so deployment needs no collectstatic step.
WHITENOISE_USE_FINDERS = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_RATES": {"login": "10/min", "register": "10/min", "otp": "5/min"},
}

# --- CORS: the React app on another origin (e.g. https://auveria-web.vercel.app) ---
# In local development Vite proxies /api, so none of this is needed.
CORS_ALLOWED_ORIGINS = _csv("CORS_ALLOWED_ORIGINS")
CORS_URLS_REGEX = r"^/api/.*$"
CORS_ALLOW_HEADERS = (*default_headers, "idempotency-key")

# --- One-time codes (OTP) ---
# Dev "SMS gateway" prints messages in the runserver terminal.
SMS_PROVIDER = "apps.security.providers.ConsoleSMSProvider"
OTP_TTL_SECONDS = 300
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 30
# Transfers at or above this amount (kobo) need an OTP. Default: N20,000.
OTP_TRANSFER_THRESHOLD_KOBO = 2_000_000

# Tests create lots of users/PINs; Django's real hashers are deliberately slow.
# Use a fast one ONLY when running `manage.py test`.
if "test" in sys.argv:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
