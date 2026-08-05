"""
Password-related views.

Handles password setup and reset through public email links.
"""

import logging

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import csrf_exempt

from drf_spectacular.utils import extend_schema

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from ..serializers import (
    CustomPasswordResetSerializer,
    PasswordResetConfirmSerializer,
    SuccessResponseSerializer,
)
from ..services import PasswordResetEmailService

logger = logging.getLogger(__name__)

@method_decorator(csrf_exempt, name='dispatch')
class SendPasswordResetEmailView(APIView):
    """
    Send a password setup or reset email with a verification link.

    A generic response prevents callers from discovering account state.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['auth'],
        summary=_("Send password setup or reset email"),
        request=CustomPasswordResetSerializer,
        responses={200: SuccessResponseSerializer}
    )
    def post(self, request):
        """
        Send a password setup or reset verification email.
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
                'message': _(
                    'Password setup or reset email sent successfully'
                ),
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_exempt, name='dispatch')
class ConfirmPasswordResetView(APIView):
    """
    Confirm password setup or reset with uid, token, and new password.

    This is the final step where user submits new password
    after clicking the link in the email.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        tags=['auth'],
        summary=_("Confirm password setup or reset"),
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
        Confirm password setup or reset.
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
                "Password setup or reset completed",
                extra={'user_id': user.pk},
            )

            return Response(
                {
                    'success': True,
                    'message': _(
                        'Password has been set successfully'
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
                    'error': _('Failed to set password'),
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
