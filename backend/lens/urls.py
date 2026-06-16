from rest_framework.routers import DefaultRouter
from django.urls import path

from .views import (
    AdminRunDetailView,
    AdminRunListView,
    AssistantViewSet,
    DataSourceViewSet,
    GlobalSettingViewSet,
    MCPServerViewSet,
    LensNodeAIGatewayView,
    LensNodeViewSet,
    PublicAssistantView,
    RunViewSet,
    SessionViewSet,
    SkillViewSet,
    run_stream_view,
)

router = DefaultRouter()
router.register("assistants", AssistantViewSet, basename="lens-assistants")
router.register("sessions", SessionViewSet, basename="lens-sessions")
router.register("runs", RunViewSet, basename="lens-runs")
router.register("admin/lensnodes", LensNodeViewSet, basename="lens-admin-lensnodes")
router.register(
    "admin/datasources",
    DataSourceViewSet,
    basename="lens-admin-datasources",
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
    *router.urls,
    path(
        "lensnode/ai-gateway/",
        LensNodeAIGatewayView.as_view(),
        name="lens-lensnode-ai-gateway",
    ),
]
