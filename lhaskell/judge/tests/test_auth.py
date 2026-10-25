from unittest import mock

from django.contrib.auth import authenticate
from django.urls import reverse

from judge.axes_backend import RequestOptionalAxesBackend

from .helpers import JudgeTestCase


class LoginTest(JudgeTestCase):
    def test_login_and_lockout(self):
        self.user("ana")
        url = reverse("judge:login")
        response = self.client.post(url, {"username": "ana", "password": "password-123"})
        self.assertRedirects(response, reverse("judge:index"), target_status_code=302)
        self.client.logout()
        for _ in range(5):
            response = self.client.post(url, {"username": "ana", "password": "wrong"})
        self.assertEqual(response.status_code, 429)
        response = self.client.post(url, {"username": "ana", "password": "password-123"})
        self.assertEqual(response.status_code, 429)  # locked even with the right password

    def test_backend_without_request(self):
        self.user("ana")
        self.assertIsNone(RequestOptionalAxesBackend().authenticate(None, username="ana", password="password-123"))
        self.assertIsNotNone(authenticate(username="ana", password="password-123"))  # ModelBackend

    def test_sentry_user(self):
        self.client.force_login(self.user("ana"))
        with mock.patch("judge.middleware.sentry_sdk.set_user") as set_user:
            self.client.get(reverse("judge:help"))
        set_user.assert_called_once()
