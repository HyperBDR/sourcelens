"""
Password-related views.

Handles password reset functionality including sending reset emails
and confirming password resets.
"""

import logging

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt

from drf_spectacular.utils import extend_schema

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ..serializers import (
    CustomPasswordResetSerializer,
    FirstTimePasswordSetupSerializer,
    PasswordResetConfirmSerializer,
    SuccessResponseSerializer,
)
from ..services import (
    PasswordResetEmailService,
    PasswordSetupEmailService,
    otp,
)

logger = logging.getLogger(__name__)

PASSWORD_ALREADY_SET = {
    "success": False,
    "error_code": "PASSWORD_ALREADY_SET",
    "message": _("A sign-in password already exists. Change it instead."),
}


@method_decorator(csrf_exempt, name='dispatch')
class SendPasswordResetEmailView(APIView):
    """
    Send password reset email with verification link.

    A generic response prevents callers from discovering account state.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['auth'],
        summary=_("Send password reset email"),
        request=CustomPasswordResetSerializer,
        responses={200: SuccessResponseSerializer}
    )
    def post(self, request):
        """
        Send password reset verification email.
        """
        serializer = CustomPasswordResetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        email = serializer.validated_data['email']
        user = (
            User.objects.select_related('profile')
            .filter(email__iexact=email)
            .first()
        )
        profile = getattr(user, 'profile', None) if user else None
        can_reset = (
            user is not None
            and user.has_usable_password()
            and profile is not None
            and profile.registration_completed
        )

        if can_reset:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            try:
                PasswordResetEmailService.send_password_reset_email(
                    email=user.email,
                    uid=uid,
                    token=token,
                    language=profile.language,
                )
            except Exception:
                logger.exception(
                    "Unexpected password reset email delivery failure",
                    extra={'user_id': user.pk},
                )

        return Response(
            {
                'success': True,
                'message': _('Password reset email sent successfully'),
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name='dispatch')
class ConfirmPasswordResetView(APIView):
    """
    Confirm password reset with uid, token, and new password.

    This is the final step where user submits new password
    after clicking the link in the email.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['auth'],
        summary=_("Confirm password reset"),
        request={
            'application/json': {
                'type': 'object',
                'properties': {
                    'uid': {
                        'type': 'string',
                        'description': 'User ID encoded in base64'
                    },
                    'token': {
                        'type': 'string',
                        'description': 'Password reset token'
                    },
                    'new_password1': {
                        'type': 'string',
                        'description': 'New password'
                    },
                    'new_password2': {
                        'type': 'string',
                        'description': 'Confirm new password'
                    }
                },
                'required': [
                    'uid',
                    'token',
                    'new_password1',
                    'new_password2'
                ]
            }
        },
        responses={200: SuccessResponseSerializer}
    )
    def post(self, request):
        """
        Confirm password reset.
        """
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = serializer.validated_data['user']
            user.set_password(serializer.validated_data['new_password1'])
            user.save(update_fields=['password'])

            logger.info(
                "Password reset completed",
                extra={'user_id': user.pk},
            )

            return Response(
                {
                    'success': True,
                    'message': _(
                        'Password has been reset successfully'
                    )
                },
                status=status.HTTP_200_OK
            )

        except Exception:
            logger.exception(
                "Failed to save a password reset",
                extra={'user_id': user.pk},
            )
            return Response(
                {
                    'success': False,
                    'error': _('Failed to reset password'),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SendPasswordSetupCodeView(APIView):
    """Send a step-up code to the authenticated account email."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["auth"],
        summary=_("Send first-time password setup code"),
        request=None,
        responses={200: SuccessResponseSerializer},
    )
    def post(self, request):
        """Issue a purpose-bound code after checking account eligibility."""
        user = request.user
        if user.has_usable_password():
            return Response(
                PASSWORD_ALREADY_SET,
                status=status.HTTP_409_CONFLICT,
            )

        email = (user.email or "").strip()
        if not email:
            return Response(
                {
                    "success": False,
                    "error_code": "EMAIL_REQUIRED",
                    "message": _("An account email is required."),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        client_ip = request.META.get("REMOTE_ADDR")
        allowed, _reason = otp.can_send(email, client_ip)
        if not allowed:
            return Response(
                {
                    "success": False,
                    "error_code": "RATE_LIMITED",
                    "message": _("Too many requests. Please try again later."),
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        code = otp.generate_code()
        otp.store_code(
            email,
            code,
            purpose=otp.PASSWORD_SETUP_PURPOSE,
        )
        profile = getattr(user, "profile", None)
        language = getattr(profile, "language", "en")
        delivered = PasswordSetupEmailService.send_password_setup_code_email(
            email,
            code,
            language,
        )
        if not delivered:
            otp.delete_code(email, purpose=otp.PASSWORD_SETUP_PURPOSE)
            return Response(
                {
                    "success": False,
                    "error_code": "DELIVERY_FAILED",
                    "message": _(
                        "Unable to send a verification code. Try again later."
                    ),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        logger.info(
            "Password setup verification code sent",
            extra={"user_id": user.pk},
        )
        return Response(
            {
                "success": True,
                "message": _("Verification code sent."),
            },
            status=status.HTTP_200_OK,
        )


class FirstTimePasswordSetupView(APIView):
    """Create a local password after fresh identity verification."""

    permission_classes = [IsAuthenticated]
    _ERROR_MESSAGES = {
        "expired": _("The verification code has expired."),
        "too_many_attempts": _(
            "Too many incorrect attempts. Request a new code."
        ),
        "invalid": _("The verification code is incorrect."),
    }

    @extend_schema(
        tags=["auth"],
        summary=_("Set first local password"),
        request=FirstTimePasswordSetupSerializer,
        responses={200: SuccessResponseSerializer},
    )
    def post(self, request):
        """Consume the step-up code and atomically create the credential."""
        if request.user.has_usable_password():
            return Response(
                PASSWORD_ALREADY_SET,
                status=status.HTTP_409_CONFLICT,
            )

        serializer = FirstTimePasswordSetupSerializer(
            data=request.data,
            context={"user": request.user},
        )
        if not serializer.is_valid():
            return Response(
                {"success": False, "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            if user.has_usable_password():
                return Response(
                    PASSWORD_ALREADY_SET,
                    status=status.HTTP_409_CONFLICT,
                )

            email = (user.email or "").strip()
            if not email:
                return Response(
                    {
                        "success": False,
                        "error_code": "EMAIL_REQUIRED",
                        "message": _("An account email is required."),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            verified, reason = otp.verify_code(
                email,
                serializer.validated_data["code"],
                purpose=otp.PASSWORD_SETUP_PURPOSE,
            )
            if not verified:
                return Response(
                    {
                        "success": False,
                        "error_code": reason.upper(),
                        "message": self._ERROR_MESSAGES.get(
                            reason,
                            _("Verification failed."),
                        ),
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.set_password(serializer.validated_data["new_password1"])
            user.save(update_fields=["password"])

        logger.info(
            "First-time password setup completed",
            extra={"user_id": user.pk},
        )
        return Response(
            {
                "success": True,
                "message": _("Password created successfully."),
            },
            status=status.HTTP_200_OK,
        )
