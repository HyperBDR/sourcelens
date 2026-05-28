"""
Views for user authentication and management.
"""

from .oauth import (
    CompleteGoogleSetupView,
    OAuthCallbackRedirectView,
)
from .registration import (
    SendRegistrationEmailView,
    VerifyRegistrationTokenView,
    CompleteRegistrationView,
    CheckVirtualEmailUsernameView,
)
from .password import (
    SendPasswordResetEmailView,
    ConfirmPasswordResetView,
)
from .user import CustomUserDetailsView
from .scenes import GetAvailableScenesView

__all__ = [
    'CompleteGoogleSetupView',
    'OAuthCallbackRedirectView',
    'SendRegistrationEmailView',
    'VerifyRegistrationTokenView',
    'CompleteRegistrationView',
    'CheckVirtualEmailUsernameView',
    'SendPasswordResetEmailView',
    'ConfirmPasswordResetView',
    'CustomUserDetailsView',
    'GetAvailableScenesView',
]
