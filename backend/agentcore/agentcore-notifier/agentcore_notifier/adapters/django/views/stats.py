"""Stats and record list API views."""
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from agentcore_notifier.adapters.django.models import NotificationRecord
from agentcore_notifier.adapters.django.services.notification_stats import (
    get_notification_record_list_from_query,
    get_notification_stats_from_query,
    get_notification_user_list,
)
from agentcore_notifier.constants import PROVIDER_DISPLAY_NAMES


class AdminNotificationStatsView(APIView):
    """
    GET: Notification statistics (summary, by_source, by_provider).
    Optional series for time buckets.
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        data = get_notification_stats_from_query(request.query_params)
        return Response(data)


class AdminNotificationRecordListView(APIView):
    """GET: Paginated notification records list."""

    permission_classes = [IsAdminUser]

    def get(self, request):
        data = get_notification_record_list_from_query(request.query_params)
        results = data.get("results", [])
        out = []
        for r in results:
            pt = r.provider_type
            out.append({
                "uuid": str(r.uuid),
                "source_app": r.source_app,
                "source_type": r.source_type,
                "source_id": r.source_id,
                "provider_type": pt,
                "provider_display_name": PROVIDER_DISPLAY_NAMES.get(pt, pt),
                "status": r.status,
                "created_at": r.created_at,
                "sent_at": r.sent_at,
                "user_id": r.user_id,
                "user_display": _user_display_from_record(r),
            })
        data["results"] = out
        return Response(data)


def _user_display_from_record(r):
    """Build user_display from record (has select_related user)."""
    if r.user:
        display = (
            getattr(r.user, "username", None)
            or getattr(r.user, "email", None)
            or getattr(r.user, "nickname", None)
        )
        if isinstance(display, str):
            display = (display or "").strip()
        if not display and r.user_id:
            return f"#{r.user_id}"
        return display or (f"#{r.user_id}" if r.user_id else None)
    return f"#{r.user_id}" if r.user_id else None


class AdminNotificationRecordDetailView(APIView):
    """GET: Single notification record by uuid (full detail for modal)."""

    permission_classes = [IsAdminUser]

    def get(self, request, uuid):
        try:
            r = (
                NotificationRecord.objects.select_related("user")
                .get(uuid=uuid)
            )
        except NotificationRecord.DoesNotExist:
            return Response(
                {"detail": "Notification record not found."},
                status=404,
            )
        pt = r.provider_type
        return Response({
            "uuid": str(r.uuid),
            "source_app": r.source_app,
            "source_type": r.source_type,
            "source_id": r.source_id,
            "source_metadata": r.source_metadata,
            "provider_type": pt,
            "provider_display_name": PROVIDER_DISPLAY_NAMES.get(pt, pt),
            "status": r.status,
            "created_at": r.created_at,
            "sent_at": r.sent_at,
            "user_id": r.user_id,
            "user_display": _user_display_from_record(r),
            "channel": r.channel,
            "target": r.target,
            "payload": r.payload,
            "template_key": r.template_key,
            "locale": r.locale,
            "content_metadata": r.content_metadata,
            "response": r.response,
            "error_message": r.error_message or None,
            "provider_message_id": r.provider_message_id or None,
            "metadata": r.metadata,
        })


class AdminNotificationUserListView(APIView):
    """
    GET: List users that have at least one notification record.
    Used for stats/records user scope dropdown.
    Returns [{"user_id": int, "display": str}].
    """

    permission_classes = [IsAdminUser]

    def get(self, request):
        data = get_notification_user_list()
        return Response(data)
