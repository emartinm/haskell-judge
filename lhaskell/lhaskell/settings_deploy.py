"""Settings loaded only in deployment (when DJANGO_DEVELOPMENT is not defined), on top of settings_shared.

Additional environment variables:
  ALLOWED_HOSTS     public host names of the judge, comma separated (required)
  SENTRY_DSN        (optional)
"""

import os

import sentry_sdk

DEBUG = False

ALLOWED_HOSTS = [host.strip() for host in os.environ["ALLOWED_HOSTS"].split(",") if host.strip()]
CSRF_TRUSTED_ORIGINS = [f"https://{host}" for host in ALLOWED_HOSTS]

# Behind a reverse proxy (nginx) that terminates TLS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

if os.environ.get("SENTRY_DSN"):
    sentry_sdk.init(
        dsn=os.environ["SENTRY_DSN"],
        # Sampling every request (as 1.0 would) is expensive and unnecessary
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
    )
