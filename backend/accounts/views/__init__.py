"""
Views for user authentication and management.
"""

from .oauth import (
    CompleteGoogleSetupView,
    OAuthCallbackRedirectView,
)
from .login_otp import (
    SendLoginCodeView,
    VerifyLoginCodeView,
)
from .registration import (
    SendRegistrationEmailView,
    VerifyRegistrationTokenView,
    CompleteRegistrationView,
    CheckVirtualEmailUsernameView,
)
from .password import (
    ConfirmPasswordResetView,
    FirstTimePasswordSetupView,
    SendPasswordResetEmailView,
    SendPasswordSetupCodeView,
)
from .user import CustomUserDetailsView
from .scenes import GetAvailableScenesView

__all__ = [
    'CompleteGoogleSetupView',
    'OAuthCallbackRedirectView',
    'SendLoginCodeView',
    'VerifyLoginCodeView',
    'SendRegistrationEmailView',
    'VerifyRegistrationTokenView',
    'CompleteRegistrationView',
    'CheckVirtualEmailUsernameView',
    'SendPasswordResetEmailView',
    'ConfirmPasswordResetView',
    'SendPasswordSetupCodeView',
    'FirstTimePasswordSetupView',
    'CustomUserDetailsView',
    'GetAvailableScenesView',
]
