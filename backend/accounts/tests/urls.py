"""URLs for accounts tests."""
from django.urls import path

from accounts.views.management import (
    ManagementGroupBulkDeleteView,
    ManagementGroupListView,
    ManagementRoleBulkView,
    ManagementUserBulkView,
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
    path(
        "api/v1/management/users/bulk-status/",
        ManagementUserBulkView.as_view(),
    ),
    path(
        "api/v1/management/groups/bulk-delete/",
        ManagementGroupBulkDeleteView.as_view(),
    ),
    path(
        "api/v1/management/roles/bulk-status/",
        ManagementRoleBulkView.as_view(),
    ),
]
