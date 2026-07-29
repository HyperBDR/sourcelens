"""Derive stable Langfuse identifiers for SourceLens runs."""

import hashlib
import uuid


def trace_id_for_run(run_uuid):
    """Return the canonical 32-hex trace identifier for a run."""

    return uuid.UUID(str(run_uuid)).hex


def root_observation_id_for_run(run_uuid):
    """Return a stable 32-hex root observation identifier for a run."""

    trace_id = trace_id_for_run(run_uuid)
    value = f"sourcelens:run:{trace_id}".encode()
    return hashlib.sha256(value).hexdigest()[:32]
