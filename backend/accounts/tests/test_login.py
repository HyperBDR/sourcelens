"""Password login identifier tests."""

from django.contrib.auth.models import User
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
