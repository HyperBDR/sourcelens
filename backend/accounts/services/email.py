"""
Email service for sending registration emails.

This service handles sending HTML emails for user registration,
supporting multiple languages with proper internationalization.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import translation
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


VERIFICATION_CODE_TEMPLATE_MAP = {
    'zh-hans': 'emails/login_otp/login_otp_email_zh.html',
    'en': 'emails/login_otp/login_otp_email_en.html',
}


def render_verification_code_email(
    code,
    expiry_minutes,
    frontend_url,
    language,
    purpose,
):
    """Render the shared verification-code email layout."""
    template = VERIFICATION_CODE_TEMPLATE_MAP.get(
        get_translation_language_code(language),
        VERIFICATION_CODE_TEMPLATE_MAP['en'],
    )
    return render_to_string(template, {
        'code': code,
        'expiry_minutes': expiry_minutes,
        'frontend_url': frontend_url,
        'purpose': purpose,
    })


def get_translation_language_code(language):
    """
    Normalize the provided language to a Django translation code.
    """
    if not language:
        return settings.LANGUAGE_CODE
    normalized = language.lower().replace('_', '-')
    mapping = getattr(settings, 'LANGUAGE_CODE_MAPPING', {})
    return mapping.get(normalized, normalized)


def get_email_delivery_options():
    """
    Resolve outbound email settings from Django settings.
    """
    from_email = (
        settings.EMAIL_HOST_USER
        if settings.EMAIL_HOST_USER
        else settings.DEFAULT_FROM_EMAIL
    )
    return from_email, None


class RegistrationEmailService:
    """
    Service class for sending registration-related emails.

    Handles email template rendering, multi-language support,
    and email delivery.
    """

    @staticmethod
    def send_registration_email(email, token, language='en'):
        """
        Send registration email with verification link.

        Args:
            email: Recipient email address
            token: Registration verification token
            language: Language code ('en', 'zh-hans')

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            template_map = {
                'zh-hans': (
                    'emails/registration/registration_email_zh.html'
                ),
                'en': (
                    'emails/registration/registration_email_en.html'
                ),
            }
            template = template_map.get(
                get_translation_language_code(language),
                template_map['en']
            )

            registration_url = (
                f"{settings.FRONTEND_URL}/register/complete/{token}"
            )

            html_content = render_to_string(template, {
                'registration_url': registration_url,
                'token': token,
            })

            translation_code = get_translation_language_code(language)
            with translation.override(translation_code):
                subject = str(_('Complete Your Registration'))
                text_content = str(_(
                    'Please complete your registration by visiting: %(url)s'
                ) % {'url': registration_url})

            from_email, connection = get_email_delivery_options()

            email_message = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[email],
                connection=connection,
            )
            email_message.attach_alternative(html_content, "text/html")

            email_message.send()

            logger.info(
                f"Sent registration email to {email} "
                f"(language: {language})"
            )
            return True

        except Exception as e:
            exception_type = type(e).__name__
            exception_msg = str(e)
            from_email_val = (
                from_email if 'from_email' in locals() else None
            )
            frontend_url = getattr(settings, 'FRONTEND_URL', None)

            error_category = 'UNKNOWN'
            exception_msg_lower = exception_msg.lower()
            if 'SMTP' in exception_type or 'smtp' in exception_msg_lower:
                error_category = 'SMTP_ERROR'
            elif (
                'connection' in exception_msg_lower or
                'timeout' in exception_msg_lower
            ):
                error_category = 'CONNECTION_ERROR'
            elif (
                'authentication' in exception_msg_lower or
                'auth' in exception_msg_lower
            ):
                error_category = 'AUTH_ERROR'
            elif 'template' in exception_msg_lower:
                error_category = 'TEMPLATE_ERROR'
            elif (
                'email' in exception_msg_lower and
                'invalid' in exception_msg_lower
            ):
                error_category = 'INVALID_EMAIL'

            logger.error(
                f"Failed to send registration email - "
                f"Email: {email}, "
                f"Language: {language}, "
                f"Template: {template}, "
                f"Error: {exception_type}: {exception_msg}, "
                f"Category: {error_category}",
                exc_info=True,
                extra={
                    'email': email,
                    'language': language,
                    'template': template,
                    'exception_type': exception_type,
                    'exception_message': exception_msg,
                    'error_category': error_category,
                    'from_email': from_email_val,
                    'frontend_url': frontend_url,
                    'service': 'RegistrationEmailService',
                }
            )
            return False


class OtpLoginEmailService:
    """
    Service class for sending email verification code (OTP) login emails.

    Sends a multipart email carrying a short-lived numeric code, reusing
    the shared verification-code layout and delivery options.
    """

    @staticmethod
    def send_login_code_email(email, code, language='en'):
        """
        Send a login verification code email.

        Args:
            email: Recipient email address
            code: Numeric verification code
            language: Language code ('en', 'zh-hans')

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            from django.conf import settings as django_settings
            expiry_minutes = max(
                1,
                getattr(django_settings, 'OTP_CODE_TTL_SECONDS', 300) // 60,
            )
            frontend_url = getattr(
                django_settings, 'FRONTEND_URL', ''
            ).rstrip('/')

            html_content = render_verification_code_email(
                code=code,
                expiry_minutes=expiry_minutes,
                frontend_url=frontend_url,
                language=language,
                purpose='login',
            )

            translation_code = get_translation_language_code(language)
            with translation.override(translation_code):
                subject = str(_('Your login verification code'))
                text_content = str(_(
                    'Your verification code is %(code)s. '
                    'It expires in %(minutes)s minutes. '
                    'If you did not request it, ignore this email.'
                ) % {'code': code, 'minutes': expiry_minutes})

            from_email, connection = get_email_delivery_options()

            email_message = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[email],
                connection=connection,
            )
            email_message.attach_alternative(html_content, 'text/html')
            email_message.send()

            logger.info(
                f"Sent login code email to {email} "
                f"(language: {language})"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to send login code email - "
                f"Email: {email}, "
                f"Language: {language}, "
                f"Error: {type(e).__name__}: {e}",
                exc_info=True,
                extra={
                    'email': email,
                    'language': language,
                    'service': 'OtpLoginEmailService',
                }
            )
            return False


class PasswordSetupEmailService:
    """Send purpose-specific step-up codes without sensitive logging."""

    @staticmethod
    def send_password_setup_code_email(email, code, language="en"):
        """Send a short-lived code for first-time password creation."""
        try:
            expiry_minutes = max(1, settings.OTP_CODE_TTL_SECONDS // 60)
            frontend_url = getattr(
                settings,
                "FRONTEND_URL",
                "",
            ).rstrip("/")
            html_content = render_verification_code_email(
                code=code,
                expiry_minutes=expiry_minutes,
                frontend_url=frontend_url,
                language=language,
                purpose="password_setup",
            )
            translation_code = get_translation_language_code(language)
            with translation.override(translation_code):
                subject = str(_("Your password setup verification code"))
                text_content = str(
                    _(
                        "Your verification code is %(code)s. "
                        "It expires in %(minutes)s minutes. "
                        "If you did not request it, ignore this email."
                    )
                    % {"code": code, "minutes": expiry_minutes}
                )

            from_email, connection = get_email_delivery_options()
            email_message = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[email],
                connection=connection,
            )
            email_message.attach_alternative(html_content, "text/html")
            email_message.send()
            logger.info("Sent password setup verification email")
            return True
        except Exception as error:
            logger.warning(
                "Failed to send password setup verification email",
                extra={
                    "error_type": type(error).__name__,
                    "service": "PasswordSetupEmailService",
                },
            )
            return False


class PasswordResetEmailService:
    """
    Service class for sending password reset emails.

    Handles email template rendering, multi-language support,
    and email delivery for password reset functionality.
    """

    @staticmethod
    def send_password_reset_email(email, uid, token, language='en'):
        """
        Send password reset email with verification link.

        Args:
            email: Recipient email address
            uid: User ID encoded in base64
            token: Password reset token from Django's token generator
            language: Language code from user profile ('en', 'zh-hans')

        Returns:
            bool: True if email sent successfully, False otherwise
        """
        try:
            template_map = {
                'zh-hans': (
                    'emails/password_reset/password_reset_email_zh.html'
                ),
                'en': (
                    'emails/password_reset/password_reset_email_en.html'
                ),
            }
            template = template_map.get(
                get_translation_language_code(language),
                template_map['en']
            )

            reset_url = (
                f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}/"
            )

            html_content = render_to_string(template, {
                'reset_url': reset_url,
                'uid': uid,
                'token': token,
                'expiry_hours': max(
                    1,
                    settings.PASSWORD_RESET_TIMEOUT // 3600,
                ),
            })

            translation_code = get_translation_language_code(language)
            with translation.override(translation_code):
                subject = str(_('Reset Your Password'))
                text_content = str(_(
                    'Please reset your password by visiting: %(url)s'
                ) % {'url': reset_url})

            from_email, connection = get_email_delivery_options()

            email_message = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=from_email,
                to=[email],
                connection=connection,
            )
            email_message.attach_alternative(html_content, "text/html")

            email_message.send()

            logger.info(
                f"Sent password reset email to {email} "
                f"(language: {language})"
            )
            return True

        except Exception as e:
            exception_type = type(e).__name__
            exception_msg = str(e)
            from_email_val = (
                from_email if 'from_email' in locals() else None
            )
            frontend_url = getattr(settings, 'FRONTEND_URL', None)

            error_category = 'UNKNOWN'
            exception_msg_lower = exception_msg.lower()
            if 'SMTP' in exception_type or 'smtp' in exception_msg_lower:
                error_category = 'SMTP_ERROR'
            elif (
                'connection' in exception_msg_lower or
                'timeout' in exception_msg_lower
            ):
                error_category = 'CONNECTION_ERROR'
            elif (
                'authentication' in exception_msg_lower or
                'auth' in exception_msg_lower
            ):
                error_category = 'AUTH_ERROR'
            elif 'template' in exception_msg_lower:
                error_category = 'TEMPLATE_ERROR'
            elif (
                'email' in exception_msg_lower and
                'invalid' in exception_msg_lower
            ):
                error_category = 'INVALID_EMAIL'

            logger.error(
                f"Failed to send password reset email - "
                f"Email: {email}, "
                f"Language: {language}, "
                f"Template: {template}, "
                f"Error: {exception_type}: {exception_msg}, "
                f"Category: {error_category}",
                exc_info=True,
                extra={
                    'email': email,
                    'language': language,
                    'template': template,
                    'exception_type': exception_type,
                    'exception_message': exception_msg,
                    'error_category': error_category,
                    'from_email': from_email_val,
                    'frontend_url': frontend_url,
                    'service': 'PasswordResetEmailService',
                }
            )
            return False
