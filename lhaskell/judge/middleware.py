"""Tags Sentry events with the authenticated user's numeric id only (no username, email or IP)."""

import sentry_sdk


class SentryUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            sentry_sdk.set_user({"id": request.user.pk})
        return self.get_response(request)
