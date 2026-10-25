"""Loads settings_shared plus settings_dev or settings_deploy depending on DJANGO_DEVELOPMENT."""

import os

from .settings_shared import *

if os.environ.get("DJANGO_DEVELOPMENT"):
    from .settings_dev import *
else:  # pragma: no cover (tests run with the development settings)
    from .settings_deploy import *
