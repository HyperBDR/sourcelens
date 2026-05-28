"""Custom DRF permissions for role-based platform access."""

from rest_framework.permissions import BasePermission

from accounts.access import get_effective_feature_keys


class HasRequiredFeature(BasePermission):
    """Allow access when the authenticated user can see the required feature."""

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False

        required_feature = getattr(view, 'required_feature', '')
        if not required_feature:
            return False

        return required_feature in get_effective_feature_keys(user)
