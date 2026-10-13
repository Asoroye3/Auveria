import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# DEV ONLY: override with an environment variable in any real deployment.
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

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

# SQLite by default. Set DB_NAME (plus DB_USER, DB_PASSWORD, DB_HOST, DB_PORT)
# to use PostgreSQL. Row locking and the concurrency tests need PostgreSQL.
if os.environ.get("DB_NAME"):
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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_RATES": {"login": "10/min", "register": "10/min", "otp": "5/min"},
}

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
