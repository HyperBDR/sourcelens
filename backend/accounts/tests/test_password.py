"""Password recovery and authenticated password change tests."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.test import TestCase
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from allauth.socialaccount.models import SocialAccount
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import Profile


class PasswordRecoveryTests(TestCase):
    """Cover password reset privacy, validation, and token behavior."""

    reset_url = "/api/v1/auth/password/reset"
    confirm_url = "/api/v1/auth/password/reset/confirm"
    strong_password = "R7vM2Qp9Lx4"

    def setUp(self):
        """Create an eligible local-password user."""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="local-user",
            email="local@example.com",
            password="Original7Qx9",
        )
        Profile.objects.update_or_create(
            user=self.user,
            defaults={"registration_completed": True, "language": "en-US"},
        )

    def request_reset(self, email):
        """Request a reset using the public API contract."""
        return self.client.post(
            self.reset_url,
            {"email": email},
            format="json",
        )

    @patch(
        "accounts.views.password.PasswordResetEmailService."
        "send_password_reset_email",
        return_value=True,
    )
    def test_reset_responses_do_not_enumerate_accounts(self, send_email):
        """Eligible and ineligible accounts return the same response."""
        oauth_user = User.objects.create_user(
            username="oauth-user",
            email="oauth@example.com",
        )
        oauth_user.set_unusable_password()
        oauth_user.save(update_fields=["password"])
        Profile.objects.update_or_create(
            user=oauth_user,
            defaults={"registration_completed": True},
        )
        SocialAccount.objects.create(
            user=oauth_user,
            provider="google",
            uid="oauth-uid",
        )
        incomplete = User.objects.create_user(
            username="incomplete-user",
            email="incomplete@example.com",
            password="Original7Qx9",
        )
        Profile.objects.update_or_create(
            user=incomplete,
            defaults={"registration_completed": False},
        )

        responses = [
            self.request_reset("local@example.com"),
            self.request_reset("unknown@example.com"),
            self.request_reset("oauth@example.com"),
            self.request_reset("incomplete@example.com"),
        ]

        self.assertTrue(
            all(response.status_code == status.HTTP_200_OK
                for response in responses)
        )
        self.assertTrue(
            all(response.data == responses[0].data for response in responses)
        )
        send_email.assert_called_once()

    @patch(
        "accounts.views.password.PasswordResetEmailService."
        "send_password_reset_email",
        side_effect=RuntimeError("SMTP unavailable"),
    )
    def test_reset_hides_delivery_failure(self, send_email):
        """Mail delivery failures do not alter the public response."""
        response = self.request_reset(self.user.email)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        self.assertNotIn("SMTP", str(response.data))
        send_email.assert_called_once()

    @patch(
        "accounts.views.password.PasswordResetEmailService."
        "send_password_reset_email",
        return_value=False,
    )
    def test_reset_hides_delivery_rejection(self, send_email):
        """A false mail result still returns the generic success response."""
        response = self.request_reset(self.user.email)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["success"])
        send_email.assert_called_once()

    def test_reset_rejects_malformed_email(self):
        """Malformed email input remains a client error."""
        response = self.request_reset("not-an-email")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def token_payload(self, password=None):
        """Build a valid camelCase confirmation payload."""
        return {
            "uid": urlsafe_base64_encode(force_bytes(self.user.pk)),
            "token": default_token_generator.make_token(self.user),
            "newPassword1": password or self.strong_password,
            "newPassword2": password or self.strong_password,
        }

    def test_reset_token_is_single_use(self):
        """A successful reset invalidates the reset token."""
        payload = self.token_payload()

        first = self.client.post(self.confirm_url, payload, format="json")
        second = self.client.post(self.confirm_url, payload, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_400_BAD_REQUEST)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.strong_password))

    def test_expired_reset_token_is_rejected(self):
        """A token older than the configured timeout cannot be used."""
        created_at = default_token_generator._now()
        with patch.object(
            default_token_generator,
            "_now",
            return_value=created_at,
        ):
            payload = self.token_payload()

        with patch.object(
            default_token_generator,
            "_now",
            return_value=created_at + timedelta(days=2),
        ):
            response = self.client.post(
                self.confirm_url,
                payload,
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_reset_link_does_not_expose_details(self):
        """Invalid identifiers return a safe validation error."""
        response = self.client.post(
            self.confirm_url,
            {
                "uid": "invalid",
                "token": "secret-reset-token",
                "newPassword1": self.strong_password,
                "newPassword2": self.strong_password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        body = str(response.data)
        self.assertNotIn("secret-reset-token", body)
        self.assertNotIn("exception", body.lower())

    def test_reset_rejects_mismatch_and_weak_passwords(self):
        """Confirmation enforces matching passwords and shared policy."""
        mismatch = self.token_payload()
        mismatch["newPassword2"] = "Another7Qx9"
        weak = self.token_payload("onlyletters")

        mismatch_response = self.client.post(
            self.confirm_url,
            mismatch,
            format="json",
        )
        weak_response = self.client.post(
            self.confirm_url,
            weak,
            format="json",
        )

        self.assertEqual(
            mismatch_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            weak_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )


class AuthenticatedPasswordChangeTests(TestCase):
    """Cover current-password checks and JWT session continuity."""

    change_url = "/api/v1/auth/password/change"
    probe_url = "/api/v1/auth/probe"
    old_password = "Original7Qx9"
    new_password = "R7vM2Qp9Lx4"

    def setUp(self):
        """Create a local user and authenticated client."""
        self.user = User.objects.create_user(
            username="change-user",
            email="change@example.com",
            password=self.old_password,
        )
        self.token = str(AccessToken.for_user(self.user))
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def payload(self, old_password=None, new_password=None):
        """Build the documented camelCase password-change payload."""
        replacement = new_password or self.new_password
        return {
            "oldPassword": old_password or self.old_password,
            "newPassword1": replacement,
            "newPassword2": replacement,
        }

    def test_password_change_requires_authentication(self):
        """Anonymous callers cannot change a password."""
        response = APIClient().post(
            self.change_url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_password_change_requires_correct_current_password(self):
        """Missing or incorrect current passwords are rejected."""
        missing = self.payload()
        del missing["oldPassword"]

        missing_response = self.client.post(
            self.change_url,
            missing,
            format="json",
        )
        wrong_response = self.client.post(
            self.change_url,
            self.payload(old_password="Wrong7Qx9"),
            format="json",
        )

        self.assertEqual(
            missing_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            wrong_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_password_change_rejects_weak_password(self):
        """Authenticated changes enforce the shared password policy."""
        response = self.client.post(
            self.change_url,
            self.payload(new_password="onlyletters"),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_change_keeps_existing_jwt_valid(self):
        """Changing a password does not terminate the active JWT session."""
        response = self.client.post(
            self.change_url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password(self.old_password))
        self.assertTrue(self.user.check_password(self.new_password))

        probe = self.client.get(self.probe_url)
        self.assertEqual(probe.status_code, status.HTTP_200_OK)
        self.assertEqual(probe.data["user_id"], self.user.pk)
