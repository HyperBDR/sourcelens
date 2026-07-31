"""Admin API for evidence-backed Run diagnostics."""

from django.core.exceptions import ValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import HasRunDiagnosticsAccess
from lens.models import Run, RunDiagnostic
from lens.run_diagnostics import (
    RunDiagnosticStateError,
    create_diagnostic_turn,
    create_run_diagnostic,
    serialize_diagnostic,
    serialize_diagnostic_turn,
)


def _get_run(run_uuid):
    return Run.objects.filter(uuid=run_uuid).first()


class AdminRunDiagnosticsView(APIView):
    """List or create diagnostics for one target Run."""

    permission_classes = [HasRunDiagnosticsAccess]

    def get(self, request, run_uuid):
        """Return diagnostics newest first."""

        del request
        run = _get_run(run_uuid)
        if run is None:
            return Response(
                {"detail": "Run not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        diagnostics = (
            RunDiagnostic.objects.filter(run=run)
            .select_related("run", "evidence", "requested_by")
            .prefetch_related("turns")
            .order_by("-created_at")
        )
        return Response([serialize_diagnostic(item) for item in diagnostics])

    def post(self, request, run_uuid):
        """Create an idempotent asynchronous diagnosis."""

        run = _get_run(run_uuid)
        if run is None:
            return Response(
                {"detail": "Run not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            diagnostic, created = create_run_diagnostic(run, request.user)
        except RunDiagnosticStateError as exc:
            return Response(
                {
                    "detail": "Only terminal Runs can be diagnosed.",
                    "code": exc.code,
                },
                status=status.HTTP_409_CONFLICT,
            )
        diagnostic = (
            RunDiagnostic.objects.select_related(
                "run",
                "evidence",
                "requested_by",
            )
            .prefetch_related("turns")
            .get(pk=diagnostic.pk)
        )
        return Response(
            serialize_diagnostic(diagnostic),
            status=(
                status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK
            ),
        )


class AdminRunDiagnosticTurnsView(APIView):
    """Create a controlled question bound to one diagnosis and target Run."""

    permission_classes = [HasRunDiagnosticsAccess]

    def post(self, request, run_uuid, diagnostic_uuid):
        """Queue one bounded follow-up question."""

        diagnostic = (
            RunDiagnostic.objects.select_related("run", "evidence")
            .filter(uuid=diagnostic_uuid, run__uuid=run_uuid)
            .first()
        )
        if diagnostic is None:
            return Response(
                {"detail": "Diagnosis not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            turn, created = create_diagnostic_turn(
                diagnostic,
                request.user,
                request.data.get("question"),
            )
        except ValidationError as exc:
            return Response(
                {
                    "detail": exc.messages[0],
                    "code": "INVALID_QUESTION",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except RunDiagnosticStateError as exc:
            return Response(
                {
                    "detail": "The diagnosis is not ready for follow-up.",
                    "code": exc.code,
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            serialize_diagnostic_turn(turn),
            status=(
                status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK
            ),
        )
