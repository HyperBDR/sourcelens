from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from accounts.services import turnstile


class TurnstileVerificationTests(SimpleTestCase):
    """Verify the explicit development bypass remains network-free."""

    @override_settings(
        TURNSTILE_ENABLED=False,
        TURNSTILE_SECRET_KEY="configured-secret",
    )
    @patch("accounts.services.turnstile.urllib.request.urlopen")
    def test_disabled_verification_bypasses_cloudflare(self, urlopen):
        passed, errors = turnstile.verify_token("")

        self.assertTrue(passed)
        self.assertEqual(errors, [])
        urlopen.assert_not_called()

    @override_settings(
        TURNSTILE_ENABLED=True,
        TURNSTILE_SECRET_KEY="configured-secret",
    )
    def test_enabled_verification_rejects_a_missing_token(self):
        passed, errors = turnstile.verify_token("")

        self.assertFalse(passed)
        self.assertEqual(errors, ["missing-input-response"])
