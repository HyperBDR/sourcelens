"""AI answer language preference tests."""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from rest_framework import status
from rest_framework.test import APIClient

from accounts.serializers import normalize_language_code
from accounts.services.registration import RegistrationService


class AnswerLanguageTests(TestCase):
    """Keep AI language choices canonical and independent from UI locales."""

    def test_new_profiles_default_to_english(self):
        """Generic user creation must not silently force Chinese answers."""

        user = User.objects.create_user(username="answer-language-default")

        self.assertEqual(user.profile.language, "en-US")

    def test_language_variants_normalize_to_supported_choices(self):
        """Only English and Chinese variants remain supported."""

        cases = {
            "en": "en-US",
            "en_us": "en-US",
            "zh": "zh-CN",
            "zh-hans": "zh-CN",
            "es-MX": "en-US",
            "ja": "en-US",
            "ko-kr": "en-US",
        }

        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_language_code(value), expected)

    def test_otp_user_without_language_defaults_to_english(self):
        """Non-browser OTP callers receive the neutral product default."""

        user = RegistrationService.get_or_create_otp_user(
            "answer-language-otp@example.com"
        )

        self.assertEqual(user.profile.language, "en-US")

    @override_settings(ROOT_URLCONF="accounts.tests.urls")
    def test_user_can_update_answer_language_through_profile_api(self):
        """The profile API persists and returns the canonical language."""

        user = User.objects.create_user(username="answer-language-api")
        client = APIClient()
        client.force_authenticate(user=user)

        response = client.patch(
            "/api/v1/auth/user",
            {"profile_language": "zh-CN"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["profile"]["language"], "zh-CN")
        user.profile.refresh_from_db()
        self.assertEqual(user.profile.language, "zh-CN")
