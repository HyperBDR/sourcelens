"""
Utility functions for working with user accounts and social authentication.
"""

from allauth.socialaccount.models import SocialAccount


class SocialAccountHelper:
    """
    Helper class for accessing social account information.

    This provides convenient methods to query OAuth provider data that was
    previously stored in Profile model fields (google_id, etc.).
    """

    @staticmethod
    def get_google_account(user):
        """
        Get user's Google account information.

        Args:
            user: Django User instance

        Returns:
            SocialAccount instance or None

        Example:
            google = SocialAccountHelper.get_google_account(user)
            if google:
                google_id = google.uid
                email = google.extra_data.get('email')
                name = google.extra_data.get('name')
                picture = google.extra_data.get('picture')
        """
        try:
            return SocialAccount.objects.get(
                user=user,
                provider='google'
            )
        except SocialAccount.DoesNotExist:
            return None

    @staticmethod
    def get_github_account(user):
        """
        Get user's GitHub account information.

        Args:
            user: Django User instance

        Returns:
            SocialAccount instance or None

        Example:
            github = SocialAccountHelper.get_github_account(user)
            if github:
                github_id = github.uid
                username = github.extra_data.get('login')
                avatar = github.extra_data.get('avatar_url')
        """
        try:
            return SocialAccount.objects.get(
                user=user,
                provider='github'
            )
        except SocialAccount.DoesNotExist:
            return None

    @staticmethod
    def get_all_social_accounts(user):
        """
        Get all social accounts linked to a user.

        Args:
            user: Django User instance

        Returns:
            QuerySet of SocialAccount instances

        Example:
            accounts = SocialAccountHelper.get_all_social_accounts(user)
            for account in accounts:
                print(
                    f"{account.provider}: {account.uid}"
                )
        """
        return SocialAccount.objects.filter(user=user)

    @staticmethod
    def has_provider(user, provider):
        """
        Check if user has linked a specific provider.

        Args:
            user: Django User instance
            provider: Provider name ('google', 'github', etc.)

        Returns:
            bool

        Example:
            if SocialAccountHelper.has_provider(user, 'google'):
                print(f"User has Google account")
        """
        return SocialAccount.objects.filter(
            user=user,
            provider=provider
        ).exists()

    @staticmethod
    def get_provider_uid(user, provider):
        """
        Get provider's user ID directly.

        This is a convenience method to get the uid without fetching
        the whole SocialAccount object.

        Args:
            user: Django User instance
            provider: Provider name

        Returns:
            str or None

        Example:
            google_id = SocialAccountHelper.get_provider_uid(
                user,
                'google'
            )
            if google_id:
                print(f"Google ID: {google_id}")
        """
        account = SocialAccount.objects.filter(
            user=user,
            provider=provider
        ).first()
        return account.uid if account else None
