"""Unified user language preference tests."""

from django.contrib.auth.models import User
from django.test import TestCase, override_settings

from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import answer_language_name
from accounts.serializers import normalize_language_code
from accounts.services.registration import RegistrationService


class LanguagePreferenceTests(TestCase):
    """Use one profile language for both the UI and generated content."""

    def test_new_profiles_keep_existing_language_default(self):
        """Removing the split setting must not require a schema migration."""

        user = User.objects.create_user(username="answer-language-default")

        self.assertEqual(user.profile.language, "zh-CN")

    def test_profile_language_keeps_existing_migration_choices(self):
        """The unified field keeps its established migration contract."""

        language_field = User._meta.apps.get_model(
            "accounts", "Profile"
        )._meta.get_field("language")

        self.assertEqual(
            [value for value, _label in language_field.choices],
            ["en-US", "zh-CN", "es", "ja-JP", "ko-KR"],
        )

    def test_language_variants_normalize_to_supported_choices(self):
        """English, Chinese, and Spanish variants remain supported."""

        cases = {
            "en": "en-US",
            "en_us": "en-US",
            "zh": "zh-CN",
            "zh-hans": "zh-CN",
            "es": "es",
            "es-MX": "es",
            "ja": "en-US",
            "ko-kr": "en-US",
        }

        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(normalize_language_code(value), expected)

    def test_spanish_uses_an_explicit_model_instruction_name(self):
        """Spanish output preferences reach model prompts as Spanish."""

        self.assertEqual(answer_language_name("es-MX"), "Spanish")

    def test_otp_user_without_language_defaults_to_english(self):
        """Non-browser OTP callers receive the neutral product default."""

        user = RegistrationService.get_or_create_otp_user(
            "answer-language-otp@example.com"
        )

        self.assertEqual(user.profile.language, "en-US")

    @override_settings(ROOT_URLCONF="accounts.tests.urls")
    def test_user_can_update_unified_language_through_profile_api(self):
        """The profile API persists the shared UI and output language."""

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
