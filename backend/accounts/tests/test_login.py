"""Password login identifier tests."""

import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient


@override_settings(
    ROOT_URLCONF="accounts.tests.urls",
    TURNSTILE_ENABLED=False,
)
class EmailPasswordLoginTests(TestCase):
    """Require an email address for password authentication."""

    login_url = "/api/v1/auth/login"
    password = "Original7Qx9"

    def setUp(self):
        """Create a user whose username and email are distinct."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="email-login-user",
            email="email-login@example.com",
            password=self.password,
        )

    def test_email_and_password_return_jwt_tokens(self):
        """A registered email is the password login identifier."""
        response = self.client.post(
            self.login_url,
            {
                "email": self.user.email,
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_username_and_password_are_rejected(self):
        """The legacy username credential no longer authenticates."""
        response = self.client.post(
            self.login_url,
            {
                "username": self.user.username,
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("access", response.data)

    def test_email_in_legacy_username_field_is_rejected(self):
        """Clients must send the new email field, not relabel username."""
        response = self.client.post(
            self.login_url,
            {
                "username": self.user.email,
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("access", response.data)

    def test_invalid_email_credentials_do_not_enumerate_accounts(self):
        """Unknown emails and wrong passwords share one public response."""
        wrong_password = self.client.post(
            self.login_url,
            {
                "email": self.user.email,
                "password": "Incorrect7Qx9",
            },
            format="json",
        )
        unknown_email = self.client.post(
            self.login_url,
            {
                "email": "unknown@example.com",
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(
            wrong_password.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(unknown_email.status_code, wrong_password.status_code)
        self.assertEqual(unknown_email.data, wrong_password.data)


@override_settings(ROOT_URLCONF="accounts.tests.urls")
class EmailCodeLoginTests(TestCase):
    """Return actionable errors for invalid email login codes."""

    verify_url = "/api/v1/auth/login/verify-code"

    def setUp(self):
        """Use DRF's JSON-aware API client."""
        self.client = APIClient()
        cache.clear()

    def _post_code(self, code="000000"):
        return self.client.post(
            self.verify_url,
            {
                "email": "code-login@example.com",
                "code": code,
            },
            format="json",
        )

    def test_malformed_code_returns_incorrect_code_message(self):
        """A code rejected by validation must not become generic failed."""
        response = self.client.post(
            self.verify_url,
            {
                "email": "code-login@example.com",
                "code": "not-a-valid-code",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "INVALID")
        self.assertEqual(
            str(response.data["message"]),
            "The verification code is incorrect.",
        )

    def test_missing_short_and_long_codes_return_invalid(self):
        payloads = (
            {"email": "code-login@example.com"},
            {"email": "code-login@example.com", "code": "12"},
            {"email": "code-login@example.com", "code": "1234567"},
        )
        for payload in payloads:
            response = self.client.post(
                self.verify_url, payload, format="json"
            )
            self.assertEqual(response.data["error_code"], "INVALID")
            self.assertNotEqual(response.data["message"], "failed")

    def test_six_digit_non_numeric_code_returns_invalid(self):
        response = self._post_code("abcdef")
        self.assertEqual(response.data["error_code"], "INVALID")
        self.assertNotEqual(response.data["message"], "failed")

    @patch("accounts.views.login_otp.otp.verify_code")
    def test_expired_code_returns_expired(self, verify_code):
        verify_code.return_value = (False, "expired")
        response = self._post_code()
        self.assertEqual(response.data["error_code"], "EXPIRED")
        self.assertIn("expired", str(response.data["message"]).lower())

    @patch("accounts.views.login_otp.otp.verify_code")
    def test_too_many_attempts_returns_stable_error(self, verify_code):
        verify_code.return_value = (False, "too_many_attempts")
        response = self._post_code()
        self.assertEqual(response.data["error_code"], "TOO_MANY_ATTEMPTS")
        self.assertIn("new code", str(response.data["message"]).lower())

    @patch("accounts.views.login_otp.otp.verify_code")
    def test_invalid_code_returns_invalid(self, verify_code):
        verify_code.return_value = (False, "invalid")
        response = self._post_code()
        self.assertEqual(response.data["error_code"], "INVALID")

    def test_renderer_keeps_error_code_inside_data(self):
        response = self._post_code("not-a-valid-code")
        response.render()
        rendered = json.loads(response.content)
        self.assertEqual(rendered["data"]["error_code"], "INVALID")
        self.assertEqual(
            rendered["data"]["message"],
            "The verification code is incorrect.",
        )
