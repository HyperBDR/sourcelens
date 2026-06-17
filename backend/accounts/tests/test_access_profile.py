from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase

from accounts.access import (
    get_access_profile,
)
from accounts.models import Role
from accounts.serializers import UserDetailsSerializer


class AccessProfileTests(TestCase):
    def test_effective_roles_include_group_union(self):
        user = User.objects.create_user(
            username='alice',
            email='alice@example.com',
            password='password123',
        )
        group = Group.objects.create(name='operators')
        role = Role.objects.create(
            name='Admins',
            visible_features=['admin_console'],
            preferred_platform='admin_console',
        )
        role.groups.add(group)
        user.groups.add(group)

        access_profile = get_access_profile(user)

        self.assertEqual(
            access_profile['visible_features'],
            ['admin_console'],
        )
        self.assertEqual(
            access_profile['preferred_platform'],
            'admin_console',
        )
        self.assertEqual(
            access_profile['landing_path'],
            '/management/users',
        )

    def test_default_features_without_roles_exclude_admin_console(self):
        user = User.objects.create_user(
            username='bob',
            email='bob@example.com',
            password='password123',
        )

        access_profile = get_access_profile(user)

        self.assertEqual(
            access_profile['visible_features'],
            [
                'workspace',
            ],
        )

    def test_user_details_serializer_includes_effective_permissions(self):
        user = User.objects.create_user(
            username='dave',
            email='dave@example.com',
            password='password123',
        )
        permission = Permission.objects.get(
            content_type__app_label='auth',
            codename='change_user',
        )
        user.user_permissions.add(permission)

        data = UserDetailsSerializer(user).data

        self.assertIn('auth.change_user', data['permissions'])
