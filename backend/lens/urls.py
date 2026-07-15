from rest_framework.routers import DefaultRouter
from django.urls import path

from .views import (
    AdminRunDetailView,
    AdminRunListView,
    AdminSharedQAViewSet,
    AssistantViewSet,
    DataSourceCredentialViewSet,
    DataSourceViewSet,
    GlobalSettingViewSet,
    LensAttachmentView,
    MCPServerViewSet,
    LensNodeAIGatewayView,
    LensNodeDeliverableUploadView,
    LensNodeSkillPackageView,
    LensNodeViewSet,
    PublicAssistantView,
    PublicSharedQAListView,
    PublicSharedQAView,
    RunViewSet,
    SessionViewSet,
    SharedQAViewSet,
    SkillViewSet,
    run_stream_view,
)

router = DefaultRouter()
router.register("assistants", AssistantViewSet, basename="lens-assistants")
router.register("sessions", SessionViewSet, basename="lens-sessions")
router.register("runs", RunViewSet, basename="lens-runs")
router.register("shares", SharedQAViewSet, basename="lens-shares")
router.register(
    "admin/shares",
    AdminSharedQAViewSet,
    basename="lens-admin-shares",
)
router.register("admin/lensnodes", LensNodeViewSet, basename="lens-admin-lensnodes")
router.register(
    "admin/datasources",
    DataSourceViewSet,
    basename="lens-admin-datasources",
)
router.register(
    "admin/credentials",
    DataSourceCredentialViewSet,
    basename="lens-admin-credentials",
)
router.register("admin/skills", SkillViewSet, basename="lens-admin-skills")
router.register(
    "admin/mcp-servers",
    MCPServerViewSet,
    basename="lens-admin-mcp-servers",
)
router.register(
    "admin/global-settings",
    GlobalSettingViewSet,
    basename="lens-admin-global-settings",
)

urlpatterns = [
    path(
        "public/assistants/<slug:slug>/",
        PublicAssistantView.as_view(),
        name="lens-public-assistant",
    ),
    path(
        "public/assistants/<slug:slug>/qa/",
        PublicSharedQAListView.as_view(),
        name="lens-public-assistant-qa",
    ),
    path(
        "public/qa/<str:token>/",
        PublicSharedQAView.as_view(),
        name="lens-public-qa",
    ),
    path(
        "runs/<uuid:uuid>/stream/",
        run_stream_view,
        name="lens-run-stream",
    ),
    path(
        "admin/runs/",
        AdminRunListView.as_view(),
        name="lens-admin-runs",
    ),
    path(
        "admin/runs/<uuid:uuid>/",
        AdminRunDetailView.as_view(),
        name="lens-admin-run-detail",
    ),
    path(
        "admin/global-settings/system-health/",
        GlobalSettingViewSet.as_view(
            {
                "get": "system_health",
                "patch": "system_health",
            }
        ),
        name="lens-admin-global-settings-system-health",
    ),
    path(
        "admin/global-settings/<str:key>/",
        GlobalSettingViewSet.as_view(
            {
                "get": "retrieve",
                "patch": "partial_update",
                "put": "update",
                "delete": "destroy",
            }
        ),
        name="lens-admin-global-settings-detail",
    ),
    path(
        "attachments/<uuid:uuid>/",
        LensAttachmentView.as_view(),
        name="lens-attachment",
    ),
    *router.urls,
    path(
        "lensnode/ai-gateway/",
        LensNodeAIGatewayView.as_view(),
        name="lens-lensnode-ai-gateway",
    ),
    path(
        "lensnode/skills/<uuid:uuid>/package/",
        LensNodeSkillPackageView.as_view(),
        name="lens-lensnode-skill-package",
    ),
    path(
        "lensnode/deliverables/",
        LensNodeDeliverableUploadView.as_view(),
        name="lens-lensnode-deliverable-upload",
    ),
]
