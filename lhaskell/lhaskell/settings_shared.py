"""
Django settings shared by development and deployment.

Everything that depends on the environment is read from environment variables:
  SECRET_KEY        (required)
  PG_DB, PG_USER, PG_PASS, PG_SERVER, PG_PORT
  EXECUTOR_SOCKET   Unix socket of haskell-test-executor
  SENTRY_DSN        (deployment only, optional)
"""

import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ["SECRET_KEY"]

DEBUG = False

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "judge.apps.JudgeConfig",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",  # Locks out repeated failed login attempts, see AUTHENTICATION_BACKENDS below
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "judge.middleware.SentryUserMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "judge.axes_backend.RequestOptionalAxesBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(hours=1)
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]

ROOT_URLCONF = "lhaskell.urls"

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

WSGI_APPLICATION = "lhaskell.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("PG_DB", "postgres"),
        "USER": os.environ.get("PG_USER", "postgres"),
        "PASSWORD": os.environ.get("PG_PASS", ""),
        "HOST": os.environ.get("PG_SERVER", "localhost"),
        "PORT": os.environ.get("PG_PORT", "9010"),
        "OPTIONS": {
            "server_side_binding": True,
            "pool": True,
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# The user interface is only in Spanish for now. Problem statements can have
# versions in several languages (see STATEMENT_LANGUAGES).
LANGUAGE_CODE = "es"
LANGUAGES = [("es", "Español")]
STATEMENT_LANGUAGES = [("es", "Español"), ("en", "English")]
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

# The application is served under /haskell/ of its domain (so that it can share the
# domain with other applications): every URL, the static files and the cookies live there.
STATIC_URL = "/haskell/static/"
STATIC_ROOT = BASE_DIR / "allstaticfiles"
LOGIN_URL = "judge:login"
LOGIN_REDIRECT_URL = "judge:index"

# Cookie names of their own: another Django application on the same domain with the
# default names would otherwise overwrite the session (logging out of one or the other).
SESSION_COOKIE_NAME = "haskell_sessionid"
SESSION_COOKIE_PATH = "/haskell/"
CSRF_COOKIE_NAME = "haskell_csrftoken"
CSRF_COOKIE_PATH = "/haskell/"

# haskell-test-executor
EXECUTOR_SOCKET = os.environ.get("EXECUTOR_SOCKET", "/run/haskell-test-executor/executor.sock")
EXECUTOR_TIMEOUT = 120  # seconds; a submission may wait in the executor queue

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "loggers": {"judge": {"handlers": ["console"], "level": "INFO"}},
}
