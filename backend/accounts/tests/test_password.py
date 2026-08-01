"""Password recovery and authenticated password change tests."""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from allauth.socialaccount.models import SocialAccount
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import Profile
from accounts.services import otp


@override_settings(ROOT_URLCONF="accounts.tests.urls")
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
            defaults={"registration_completed": True, "language": "en"},
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


@override_settings(
    ROOT_URLCONF="accounts.tests.urls",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    OTP_CODE_TTL_SECONDS=300,
    OTP_MAX_ATTEMPTS=5,
    OTP_SEND_COOLDOWN_SECONDS=0,
    OTP_SEND_MAX_PER_DAY=10,
    OTP_SEND_MAX_PER_IP_HOUR=20,
)
class FirstTimePasswordSetupTests(TestCase):
    """Cover step-up verification and first-time password creation."""

    send_code_url = "/api/v1/auth/password/setup/send-code"
    setup_url = "/api/v1/auth/password/setup"
    probe_url = "/api/v1/auth/probe"
    code = "482731"
    strong_password = "R7vM2Qp9Lx4"

    def setUp(self):
        """Create a passwordless user with an authenticated client."""
        cache.clear()
        self.user = User.objects.create_user(
            username="passwordless-user",
            email="passwordless@example.com",
        )
        self.user.set_unusable_password()
        self.user.save(update_fields=["password"])
        Profile.objects.update_or_create(
            user=self.user,
            defaults={"registration_completed": True, "language": "en"},
        )
        self.token = str(AccessToken.for_user(self.user))
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token}")

    def tearDown(self):
        """Remove OTP cache state between tests."""
        cache.clear()

    def payload(self, code=None, password=None):
        """Build the documented camelCase setup payload."""
        replacement = password or self.strong_password
        return {
            "code": code or self.code,
            "newPassword1": replacement,
            "newPassword2": replacement,
        }

    def store_setup_code(self, email=None, code=None):
        """Store a password-setup code for a test account."""
        otp.store_code(
            email or self.user.email,
            code or self.code,
            purpose="password_setup",
        )

    def test_setup_endpoints_require_authentication(self):
        """Anonymous callers cannot issue or consume setup codes."""
        anonymous = APIClient()

        send_response = anonymous.post(self.send_code_url, {}, format="json")
        setup_response = anonymous.post(
            self.setup_url,
            self.payload(),
            format="json",
        )

        self.assertEqual(
            send_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            setup_response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    @patch("accounts.services.otp.generate_code", return_value=code)
    def test_send_code_targets_authenticated_users_email(self, generate_code):
        """The server chooses the destination from the current account."""
        response = self.client.post(
            self.send_code_url,
            {"email": "attacker@example.com"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn(self.code, mail.outbox[0].body)
        generate_code.assert_called_once_with()

    @patch("accounts.services.otp.can_send", return_value=(False, "cooldown"))
    def test_send_code_preserves_rate_limits(self, can_send):
        """Step-up email issuance uses the existing OTP rate limits."""
        response = self.client.post(self.send_code_url, {}, format="json")

        self.assertEqual(
            response.status_code,
            status.HTTP_429_TOO_MANY_REQUESTS,
        )
        self.assertEqual(response.data["error_code"], "RATE_LIMITED")
        self.assertEqual(len(mail.outbox), 0)
        can_send.assert_called_once_with(self.user.email, "127.0.0.1")

    def test_users_with_password_are_directed_to_change_flow(self):
        """Existing local-password users cannot enter first-time setup."""
        self.user.set_password("Original7Qx9")
        self.user.save(update_fields=["password"])

        send_response = self.client.post(self.send_code_url, {}, format="json")
        setup_response = self.client.post(
            self.setup_url,
            self.payload(),
            format="json",
        )

        self.assertEqual(send_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(setup_response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            setup_response.data["error_code"],
            "PASSWORD_ALREADY_SET",
        )

    def test_login_code_cannot_authorize_password_setup(self):
        """A public login code is not valid for credential creation."""
        otp.store_code(self.user.email, self.code)

        response = self.client.post(
            self.setup_url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "EXPIRED")
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
        self.assertEqual(
            otp.verify_code(self.user.email, self.code),
            (True, ""),
        )

    def test_code_is_bound_to_current_account_email(self):
        """A code issued for another email cannot change this account."""
        self.store_setup_code(email="other@example.com")

        response = self.client.post(
            self.setup_url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error_code"], "EXPIRED")

    def test_expired_invalid_and_attempt_limited_codes_are_rejected(self):
        """Step-up verification preserves expiry and retry protections."""
        expired = self.client.post(
            self.setup_url,
            self.payload(),
            format="json",
        )
        self.store_setup_code()
        invalid_responses = [
            self.client.post(
                self.setup_url,
                self.payload(code="000000"),
                format="json",
            )
            for _ in range(5)
        ]

        self.assertEqual(expired.data["error_code"], "EXPIRED")
        self.assertTrue(
            all(
                response.status_code == status.HTTP_400_BAD_REQUEST
                for response in invalid_responses
            )
        )
        self.assertEqual(
            invalid_responses[-1].data["error_code"],
            "TOO_MANY_ATTEMPTS",
        )
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    def test_setup_rejects_mismatch_weak_and_malformed_passwords(self):
        """The server enforces confirmation and the shared password policy."""
        mismatch = self.payload()
        mismatch["newPassword2"] = "Another7Qx9"

        mismatch_response = self.client.post(
            self.setup_url,
            mismatch,
            format="json",
        )
        weak_response = self.client.post(
            self.setup_url,
            self.payload(password="onlyletters"),
            format="json",
        )
        malformed_response = self.client.post(
            self.setup_url,
            {"code": "123"},
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
        self.assertEqual(
            malformed_response.status_code,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_success_sets_password_keeps_jwt_and_audits_safely(self):
        """Successful setup updates auth state without rotating the JWT."""
        self.store_setup_code()

        with self.assertLogs("accounts.views.password", level="INFO") as logs:
            response = self.client.post(
                self.setup_url,
                self.payload(),
                format="json",
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertNotIn(self.code, str(response.data))
        self.assertNotIn(self.strong_password, str(response.data))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.strong_password))

        probe = self.client.get(self.probe_url)
        self.assertEqual(probe.status_code, status.HTTP_200_OK)
        self.assertEqual(probe.data["user_id"], self.user.pk)
        log_output = " ".join(logs.output)
        self.assertIn("First-time password setup completed", log_output)
        self.assertNotIn(self.user.email, log_output)
        self.assertNotIn(self.code, log_output)
        self.assertNotIn(self.strong_password, log_output)

    def test_reused_code_and_double_submission_have_stable_conflict(self):
        """A repeated submission cannot replace the newly created password."""
        self.store_setup_code()
        first = self.client.post(
            self.setup_url,
            self.payload(),
            format="json",
        )
        second = self.client.post(
            self.setup_url,
            self.payload(password="Different7Qx9"),
            format="json",
        )

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            second.data["error_code"],
            "PASSWORD_ALREADY_SET",
        )
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.strong_password))
        self.assertFalse(self.user.check_password("Different7Qx9"))


@override_settings(ROOT_URLCONF="accounts.tests.urls")
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
