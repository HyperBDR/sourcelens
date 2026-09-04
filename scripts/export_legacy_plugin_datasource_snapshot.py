"""Emit non-secret legacy datasource configuration for conversion."""

import json
import sys

from lens.models import DataSource


datasources = [
    {
        "uuid": str(datasource.uuid),
        "name": datasource.name,
        "source_type": datasource.source_type,
        "credential_provider": (
            datasource.credential.provider
            if datasource.credential_id
            else ""
        ),
        "credential_endpoint_url": (
            datasource.credential.endpoint_url
            if datasource.credential_id
            else ""
        ),
        "config": datasource.config,
        "sync_policy": datasource.sync_policy,
        "target_path": datasource.target_path,
        "status": datasource.status,
    }
    for datasource in DataSource.objects.select_related(
        "credential",
    ).order_by("pk")
]
sys.stdout.write(
    json.dumps(
        {
            "schema_version": 1,
            "datasources": datasources,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )
)
