from django.test import SimpleTestCase, override_settings

from accounts.services.email import get_email_delivery_options


class EmailDeliveryOptionsTests(SimpleTestCase):
    @override_settings(
        EMAIL_HOST_USER='env-user@example.com',
        DEFAULT_FROM_EMAIL='noreply@example.com',
    )
    def test_uses_email_host_user_when_configured(self):
        from_email, connection = get_email_delivery_options()

        assert from_email == 'env-user@example.com'
        assert connection is None

    @override_settings(
        EMAIL_HOST_USER='',
        DEFAULT_FROM_EMAIL='noreply@example.com',
    )
    def test_uses_default_from_email_when_host_user_is_empty(self):
        from_email, connection = get_email_delivery_options()

        assert from_email == 'noreply@example.com'
        assert connection is None
