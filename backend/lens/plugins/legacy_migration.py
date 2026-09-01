"""Reversible migration from legacy GitHub credentials to Connections."""

from urllib.parse import urlsplit

from django.db import transaction
from django.utils import timezone

from lens.models import (
    Connection,
    DataSource,
    DataSourceCredential,
    LegacyIntegrationMigration,
    SecretMaterial,
    SecretVersion,
)


def migrate_legacy_github_integrations(dry_run=False):
    """Migrate unambiguous GitHub token consumers and audit every decision."""

    report = {"migrated": 0, "manual_review": 0, "skipped": 0}
    credentials = DataSourceCredential.objects.order_by("pk")
    for credential in credentials:
        if LegacyIntegrationMigration.objects.filter(
            source_kind=LegacyIntegrationMigration.SourceKind.CREDENTIAL,
            source_uuid=credential.uuid,
            status=LegacyIntegrationMigration.Status.MIGRATED,
        ).exists():
            report["skipped"] += 1
            continue
        _migrate_credential(credential, report, dry_run)
    return report


def rollback_legacy_github_integrations():
    """Restore legacy datasource execution and disable migrated Connections."""

    records = LegacyIntegrationMigration.objects.filter(
        source_kind=LegacyIntegrationMigration.SourceKind.DATASOURCE,
        status=LegacyIntegrationMigration.Status.MIGRATED,
    ).select_related("datasource", "connection")
    connection_ids = set()
    rolled_back = 0
    with transaction.atomic():
        for record in records:
            datasource = record.datasource
            if datasource is None:
                continue
            datasource.connection = None
            datasource.plugin_key = ""
            datasource.datasource_config = {}
            datasource.save(
                update_fields=[
                    "connection",
                    "plugin_key",
                    "datasource_config",
                    "updated_at",
                ]
            )
            if record.connection_id:
                connection_ids.add(record.connection_id)
            record.status = LegacyIntegrationMigration.Status.ROLLED_BACK
            record.save(update_fields=["status", "updated_at"])
            rolled_back += 1
        Connection.objects.filter(pk__in=connection_ids).update(
            status=Connection.Status.DISABLED,
            updated_at=timezone.now(),
        )
        LegacyIntegrationMigration.objects.filter(
            source_kind=LegacyIntegrationMigration.SourceKind.CREDENTIAL,
            connection_id__in=connection_ids,
            status=LegacyIntegrationMigration.Status.MIGRATED,
        ).update(status=LegacyIntegrationMigration.Status.ROLLED_BACK)
    return {"rolled_back": rolled_back}


def _migrate_credential(credential, report, dry_run):
    reason = _credential_reason(credential)
    datasources = list(
        credential.datasources.filter(
            source_type=DataSource.SourceType.GIT,
            connection__isnull=True,
        ).order_by("pk")
    )
    parsed = []
    for datasource in datasources:
        resource, datasource_reason = _datasource_resource(datasource)
        if datasource_reason:
            _record_manual(
                datasource.uuid,
                LegacyIntegrationMigration.SourceKind.DATASOURCE,
                datasource_reason,
                report,
                dry_run,
                datasource=datasource,
            )
        elif reason:
            _record_manual(
                datasource.uuid,
                LegacyIntegrationMigration.SourceKind.DATASOURCE,
                reason,
                report,
                dry_run,
                datasource=datasource,
            )
        elif not _resource_in_legacy_scope(
            resource["repository"],
            credential.scope_config,
        ):
            _record_manual(
                datasource.uuid,
                LegacyIntegrationMigration.SourceKind.DATASOURCE,
                "RESOURCE_OUTSIDE_LEGACY_SCOPE",
                report,
                dry_run,
                datasource=datasource,
            )
        else:
            parsed.append((datasource, resource))
    if reason or not parsed:
        _record_manual(
            credential.uuid,
            LegacyIntegrationMigration.SourceKind.CREDENTIAL,
            reason or "NO_UNAMBIGUOUS_DATASOURCE",
            report,
            dry_run,
        )
        return
    report["migrated"] += len(parsed) + 1
    if dry_run:
        return
    with transaction.atomic():
        material = SecretMaterial.objects.create(
            name=f"{credential.name} migrated secret"
        )
        version = SecretVersion(material=material)
        version.set_value(credential.get_secret())
        version.save()
        repositories = sorted(
            {resource["repository"] for _, resource in parsed},
            key=str.casefold,
        )
        connection = Connection.objects.create(
            name=credential.name,
            plugin_key="github",
            endpoint="https://github.com",
            allowed_scope={"repositories": repositories},
            secret_version=version,
        )
        _upsert_record(
            credential.uuid,
            LegacyIntegrationMigration.SourceKind.CREDENTIAL,
            LegacyIntegrationMigration.Status.MIGRATED,
            "",
            connection=connection,
            details={"datasource_count": len(parsed)},
        )
        for datasource, resource in parsed:
            datasource.connection = connection
            datasource.plugin_key = "github"
            datasource.datasource_config = resource
            datasource.save(
                update_fields=[
                    "connection",
                    "plugin_key",
                    "datasource_config",
                    "updated_at",
                ]
            )
            _upsert_record(
                datasource.uuid,
                LegacyIntegrationMigration.SourceKind.DATASOURCE,
                LegacyIntegrationMigration.Status.MIGRATED,
                "",
                connection=connection,
                datasource=datasource,
                details={"repository": resource["repository"]},
            )


def _credential_reason(credential):
    if credential.provider != DataSourceCredential.Provider.GITHUB:
        return "PROVIDER_UNSUPPORTED"
    if credential.auth_type != DataSourceCredential.AuthType.HTTPS_TOKEN:
        return "AUTH_TYPE_UNSUPPORTED"
    if not credential.get_secret():
        return "SECRET_UNAVAILABLE"
    endpoint = str(credential.endpoint_url or "https://github.com").rstrip("/")
    if endpoint != "https://github.com":
        return "ENDPOINT_UNSUPPORTED"
    return ""


def _datasource_resource(datasource):
    config = datasource.config or {}
    if config.get("scope_type") == "organization" or config.get("repositories"):
        return None, "ORGANIZATION_DATASOURCE_AMBIGUOUS"
    repository = _github_repository(config.get("repo_url"))
    if not repository:
        return None, "REPOSITORY_URL_UNSUPPORTED"
    resource = {"repository": repository}
    branch = str(config.get("branch") or "").strip()
    if branch:
        resource["branch"] = branch
    directory = str(config.get("directory") or "").strip()
    if directory:
        resource["directory"] = directory
    return resource, ""


def _github_repository(value):
    parsed = urlsplit(str(value or "").strip())
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.username
        or parsed.password
        or parsed.port
        or parsed.query
        or parsed.fragment
    ):
        return ""
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) != 2:
        return ""
    owner, repository = parts
    if repository.endswith(".git"):
        repository = repository[:-4]
    if not owner or not repository:
        return ""
    return f"{owner}/{repository}"


def _resource_in_legacy_scope(repository, scope_config):
    scope_url = str((scope_config or {}).get("organization_url") or "").strip()
    if not scope_url:
        return True
    parsed = urlsplit(scope_url)
    if parsed.scheme != "https" or parsed.hostname != "github.com":
        return False
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    repository_parts = repository.split("/")
    if len(parts) == 1:
        return parts[0].casefold() == repository_parts[0].casefold()
    scoped_repository = _github_repository(scope_url)
    return bool(scoped_repository) and (
        scoped_repository.casefold() == repository.casefold()
    )


def _record_manual(
    source_uuid,
    source_kind,
    reason,
    report,
    dry_run,
    datasource=None,
):
    report["manual_review"] += 1
    if dry_run:
        return
    _upsert_record(
        source_uuid,
        source_kind,
        LegacyIntegrationMigration.Status.MANUAL_REVIEW,
        reason,
        datasource=datasource,
    )


def _upsert_record(source_uuid, source_kind, status, reason, **values):
    LegacyIntegrationMigration.objects.update_or_create(
        source_kind=source_kind,
        source_uuid=source_uuid,
        defaults={"status": status, "reason": reason, **values},
    )
