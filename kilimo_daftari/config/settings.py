"""
Django settings for the KALRO Advisory Content & Provider Platform backend.

This service is the "Provider Platform" system of record in the KilimoSTACK /
OpenAgriNet (OAN) Beckn architecture: it stores, screens and classifies KALRO's
agricultural advisory content (per the Advisory Content Import JSON
Specification v0.1) and exposes it to:

  1. A downstream Beckn Adaptor - Provider (client-facing side), so KALRO can
     be discovered/transacted with as a registered provider on the KilimoSTACK
     open network.
  2. The FastAPI + Ollama "AI Layer" service (ai_layer/), which pulls/receives
     certified content to build the RAG vector index.
"""

import os
from pathlib import Path

import dj_database_url

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-secret-key-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    # "unfold",
    "admin_interface",
    "colorfield",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "django_filters",
    "import_export",
    
    "advisory",
    "beckn_provider",
    "providers",
    "accounts",
]

X_FRAME_OPTIONS = "SAMEORIGIN"
SILENCED_SYSTEM_CHECKS = ["security.W019",]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Default: SQLite for local/dev use. Set DATABASE_URL (e.g. in docker-compose)
# to point at Postgres for a production-like setup.
# DATABASES = {
#     "default": dj_database_url.config(
#         default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
#         conn_max_age=600,
#     )
# }

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DB_NAME', 'mydb'),
        'USER': os.environ.get('DB_USER', 'myuser'),
        'PASSWORD': os.environ.get('DB_PASSWORD', 'mypassword'),
        'HOST': os.environ.get('DB_HOST', 'localhost'),
        'PORT': os.environ.get('DB_PORT', '5432'),
        'CONN_MAX_AGE': 600,  # Persistent connections (in seconds)
        'OPTIONS': {
            # 'sslmode': os.environ.get('DB_SSLMODE', 'require'),
            'connect_timeout': 10,
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
# The frontend (Vite dev server on a different port, or a separately hosted
# production build) calls this API directly from the browser, which enforces
# CORS -- unlike server-to-server or Node-based calls, which ignore it. Set
# CORS_ALLOWED_ORIGINS to your real frontend origin(s) in production; the
# default covers the Vite dev server and the docker-compose frontend port.
_cors_env = os.environ.get("DJANGO_CORS_ALLOWED_ORIGINS", "")
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_env.split(",") if o.strip()] or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CORS_ALLOW_ALL_ORIGINS = os.environ.get("DJANGO_CORS_ALLOW_ALL", "false").lower() == "true"

# ---------------------------------------------------------------------------
# KilimoSTACK / AI Layer integration settings
# ---------------------------------------------------------------------------
# When an AdvisoryResource is created/updated and its quality_flag is
# "Ready to Certify", the advisory app will best-effort POST it to the
# FastAPI AI Layer's /ingest endpoint so the RAG vector index stays current.
AI_LAYER_BASE_URL = os.environ.get("AI_LAYER_BASE_URL", "http://localhost:8001")
AI_LAYER_INGEST_PATH = "/api/v1/ingest"
AI_LAYER_SYNC_TIMEOUT_SECONDS = float(os.environ.get("AI_LAYER_SYNC_TIMEOUT_SECONDS", "5"))
AI_LAYER_SYNC_ENABLED = os.environ.get("AI_LAYER_SYNC_ENABLED", "true").lower() == "true"

# Institution identity used when this instance registers itself as a
# provider on the KilimoSTACK / Beckn network.
PROVIDER_INSTITUTION_NAME = os.environ.get(
    "PROVIDER_INSTITUTION_NAME", "Kenya Agricultural and Livestock Research Organization"
)
PROVIDER_ID = os.environ.get("PROVIDER_ID", "kalro.kilimostack")
