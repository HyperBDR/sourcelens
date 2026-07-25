from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from lens.environment_variables import (
    validate_environment_schema,
    validate_environment_values,
)


class EnvironmentVariableNameTests(SimpleTestCase):
    """Portable uppercase Shell environment-variable name contract."""

    def test_accepts_shell_safe_uppercase_names(self):
        valid_names = [
            "API_TOKEN",
            "_PRIVATE_KEY",
            "SERVICE_URL_2",
        ]

        for name in valid_names:
            with self.subTest(name=name):
                schema = validate_environment_schema([{"name": name}])
                values = validate_environment_values({name: "value"})

                self.assertEqual(schema[0]["name"], name)
                self.assertEqual(values[name], "value")

    def test_rejects_names_that_are_not_shell_safe_uppercase_identifiers(self):
        invalid_names = [
            "2FA_TOKEN",
            "api_token",
            "API-TOKEN",
            "API.TOKEN",
            "API TOKEN",
            "API=TOKEN",
        ]

        for name in invalid_names:
            with self.subTest(name=name):
                with self.assertRaises(ValidationError):
                    validate_environment_schema([{"name": name}])
                with self.assertRaises(ValidationError):
                    validate_environment_values({name: "value"})
