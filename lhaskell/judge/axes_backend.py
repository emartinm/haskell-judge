"""Authentication backend that makes django-axes tolerate authenticate() calls without a request."""

from axes.backends import AxesBackend


class RequestOptionalAxesBackend(AxesBackend):
    """AxesBackend raises a ValueError (not PermissionDenied) when authenticate() is called
    without a request, which crashes the caller. Every real login (LoginView) carries a
    request; only Django's test Client.login() omits it. Without a request this backend
    defers to the next one (ModelBackend), so real logins remain protected by axes."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if request is None:
            return None
        return super().authenticate(request, username=username, password=password, **kwargs)
