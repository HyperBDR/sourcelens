"""Shared Q&A publishing, moderation, and public views."""

import secrets

from django.db.models import F
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from lens.models import Assistant, SharedQA
from lens.serializers import (
    SharedQAAdminSerializer,
    SharedQAListSerializer,
    SharedQAMineSerializer,
    SharedQAPublicSerializer,
)
from .admin_runs import _admin_safe_int
from .base import BaseAdminViewSet, BaseAuthenticatedViewSet


def _unique_share_token():
    """Generate a collision-free URL-safe share token."""

    for _ in range(5):
        token = secrets.token_urlsafe(16)
        if not SharedQA.objects.filter(token=token).exists():
            return token
    return secrets.token_urlsafe(24)


def _shared_qa_default_title(question, limit=60):
    """Derive a default share title from the question text."""

    text = " ".join((question or "").split())
    return text[:limit] or "Shared Q&A"


class SharedQAViewSet(BaseAuthenticatedViewSet):
    """List, rename, and revoke the current user's own shared Q&As."""

    queryset = SharedQA.objects.all().select_related("published_by")
    serializer_class = SharedQAMineSerializer
    http_method_names = ["get", "patch", "delete", "head", "options"]

    def get_queryset(self):
        """Restrict to shares published by the current user."""

        return super().get_queryset().filter(
            published_by=self.request.user
        )

    def partial_update(self, request, *args, **kwargs):
        """Let the owner edit the share title after publishing."""

        share = self.get_object()
        title = (request.data.get("title") or "").strip()
        if title:
            share.title = title[:200]
            share.save(update_fields=["title", "updated_at"])
        return Response(SharedQAMineSerializer(share).data)


class AdminSharedQAViewSet(BaseAdminViewSet):
    """Admin moderation/curation of shared Q&As."""

    queryset = SharedQA.objects.all().select_related("published_by")
    serializer_class = SharedQAAdminSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        """Filter by listed/status for the moderation queue."""

        queryset = super().get_queryset()
        params = self.request.query_params
        listed = params.get("listed")
        if listed in ("true", "false"):
            queryset = queryset.filter(is_listed=(listed == "true"))
        status_param = (params.get("status") or "").strip()
        if status_param:
            queryset = queryset.filter(status=status_param)
        return queryset


class PublicSharedQAView(APIView):
    """Single shared Q&A by token with assistant visibility rules."""

    permission_classes = [permissions.AllowAny]

    def get(self, request, token):
        """Return one published shared Q&A and bump its view count."""

        share = (
            SharedQA.objects.select_related("assistant", "published_by")
            .filter(token=token, status=SharedQA.Status.PUBLISHED)
            .first()
        )
        if share is None or not _shared_qa_visible_to_user(
            share,
            request.user,
        ):
            return Response(
                {"detail": "Shared Q&A not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        SharedQA.objects.filter(pk=share.pk).update(
            view_count=F("view_count") + 1
        )
        share.refresh_from_db(fields=["view_count"])
        return Response(SharedQAPublicSerializer(share).data)


def _shared_qa_visible_to_user(share, user):
    """Return whether a shared Q&A may be read through its token."""

    if share.is_listed:
        return True
    if not (user and user.is_authenticated):
        return False
    if user.is_staff or user.is_superuser:
        return True
    if share.published_by_id == user.id:
        return True
    publisher = share.published_by
    if publisher is None:
        return False
    return publisher.groups.filter(pk__in=user.groups.values("pk")).exists()


class PublicSharedQAListView(APIView):
    """Public list of an assistant's curated shared Q&As (anonymous)."""

    authentication_classes = []
    permission_classes = []

    def get(self, request, slug):
        """Return curated, listed shares for one active assistant."""

        assistant = Assistant.objects.filter(
            slug=slug,
            status=Assistant.Status.ACTIVE,
        ).first()
        if assistant is None:
            return Response(
                {"detail": "Assistant not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        params = request.query_params
        limit = _admin_safe_int(params.get("limit"), 20, maximum=50)
        offset = _admin_safe_int(params.get("offset"), 0, minimum=0)
        queryset = SharedQA.objects.filter(
            assistant=assistant,
            is_listed=True,
            status=SharedQA.Status.PUBLISHED,
        ).order_by("-published_at", "-created_at")
        total = queryset.count()
        rows = SharedQAListSerializer(
            queryset[offset:offset + limit],
            many=True,
        ).data
        has_more = offset + limit < total
        return Response({
            "assistant": {"name": assistant.name, "slug": assistant.slug},
            "results": rows,
            "total": total,
            "next_offset": offset + limit if has_more else None,
        })
