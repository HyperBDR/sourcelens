"""URLs for accounts tests."""
from django.urls import path

from accounts.views.management import (
    ManagementGroupListView,
    ManagementUserListView,
)


urlpatterns = [
    path(
        "api/v1/management/users/",
        ManagementUserListView.as_view(),
    ),
    path(
        "api/v1/management/groups/",
        ManagementGroupListView.as_view(),
    ),
]
