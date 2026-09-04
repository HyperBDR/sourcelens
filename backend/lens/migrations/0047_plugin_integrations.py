import hashlib
import json
import uuid
from pathlib import Path

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


TOKEN_BUDGET_PROFILE_BY_AGENT_ROUNDS = {
    "flash": "standard",
    "fast": "standard",
    "balanced": "standard",
    "deep": "deep",
    "max": "unlimited",
}


def bind_token_budget_to_agent_rounds(apps, schema_editor):
    """Align existing Assistants with the execution strategy mapping."""

    assistant_model = apps.get_model("lens", "Assistant")
    profiles = TOKEN_BUDGET_PROFILE_BY_AGENT_ROUNDS.items()
    for agent_rounds, token_budget_profile in profiles:
        assistant_model.objects.filter(agent_rounds=agent_rounds).update(
            token_budget_profile=token_budget_profile
        )


def _plugin_package_digest(package):
    """Return the immutable content identity for one bundled Plugin."""

    digest = hashlib.sha256()
    files = []
    for path in package.rglob("*"):
        relative = path.relative_to(package)
        if "__pycache__" in relative.parts or path.suffix == ".pyc":
            continue
        if path.is_file() and not path.is_symlink():
            files.append((relative.as_posix(), path))
    for relative, path in sorted(files):
        content = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\0")
        digest.update(content)
    return digest.hexdigest()


def bootstrap_plugin_releases(apps, schema_editor):
    """Mark the latest bundled version active on existing installations."""

    del schema_editor
    release_model = apps.get_model("lens", "PluginRelease")
    installed = {}
    for root_value in settings.LENS_PLUGIN_ROOTS:
        root = Path(root_value)
        if not root.is_dir() or root.is_symlink():
            continue
        for manifest_path in root.glob("*/*/plugin.json"):
            package = manifest_path.parent
            if package.is_symlink():
                continue
            try:
                manifest = json.loads(manifest_path.read_text("utf-8"))
                key = manifest["key"]
                version = manifest["version"]
                version_key = tuple(int(part) for part in version.split("."))
            except (KeyError, OSError, TypeError, ValueError):
                continue
            if package.parent.name != key or package.name != version:
                continue
            installed[(key, version)] = (version_key, package)
    by_key = {}
    for (key, version), (version_key, package) in installed.items():
        by_key.setdefault(key, []).append((version_key, version, package))
    for key, releases in by_key.items():
        releases.sort()
        active_version = releases[-1][1]
        for _version_key, version, package in releases:
            is_active = version == active_version
            release_model.objects.create(
                plugin_key=key,
                version=version,
                package_digest=_plugin_package_digest(package),
                release_status="published" if is_active else "debugging",
                deployment_role="active" if is_active else "",
                published_at=timezone.now() if is_active else None,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("lens", "0046_assistant_fixed_collaboration"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Connection",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("plugin_key", models.CharField(max_length=64)),
                ("endpoint", models.URLField(max_length=500)),
                ("config", models.JSONField(blank=True, default=dict)),
                ("allowed_scope", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("disabled", "Disabled")],
                        default="active",
                        max_length=16,
                    ),
                ),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="SecretMaterial",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=160)),
                ("status", models.CharField(default="active", max_length=16)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="PluginRelease",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("plugin_key", models.CharField(max_length=64)),
                ("version", models.CharField(max_length=32)),
                ("package_digest", models.CharField(max_length=64)),
                (
                    "release_status",
                    models.CharField(
                        choices=[
                            ("debugging", "Debugging"),
                            ("published", "Published"),
                            ("retired", "Retired"),
                        ],
                        default="debugging",
                        max_length=16,
                    ),
                ),
                (
                    "deployment_role",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", "None"),
                            ("candidate", "Candidate"),
                            ("active", "Active"),
                        ],
                        default="",
                        max_length=16,
                    ),
                ),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                (
                    "published_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="published_plugin_releases",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["plugin_key", "-version"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("plugin_key", "version"),
                        name="lens_plugin_release_identity_uniq",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("deployment_role", "active")),
                        fields=("plugin_key",),
                        name="lens_plugin_release_active_uniq",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("deployment_role", "candidate")),
                        fields=("plugin_key",),
                        name="lens_plugin_release_candidate_uniq",
                    ),
                    models.CheckConstraint(
                        condition=(
                            models.Q(("deployment_role", ""))
                            | models.Q(
                                ("deployment_role__in", ["active", "candidate"]),
                                ("release_status", "published"),
                            )
                        ),
                        name="lens_plugin_release_role_status_ck",
                    ),
                ],
            },
        ),
        migrations.AddField(
            model_name="datasource",
            name="datasource_config",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="datasource",
            name="plugin_key",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="datasource",
            name="connection",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="datasources",
                to="lens.connection",
            ),
        ),
        migrations.CreateModel(
            name="SecretVersion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("encrypted_value", models.TextField()),
                ("status", models.CharField(default="active", max_length=16)),
                (
                    "material",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="versions",
                        to="lens.secretmaterial",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="ExecutionSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("datasource_sync", "Datasource Sync"),
                            ("tool_invoke", "Tool Invoke"),
                        ],
                        max_length=32,
                    ),
                ),
                ("plugin_key", models.CharField(max_length=64)),
                ("plugin_version", models.CharField(max_length=32)),
                ("protocol_version", models.PositiveIntegerField()),
                ("resolved_config", models.JSONField(default=dict)),
                (
                    "connection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="execution_snapshots",
                        to="lens.connection",
                    ),
                ),
                (
                    "datasource",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="execution_snapshots",
                        to="lens.datasource",
                    ),
                ),
                (
                    "secret_version",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="execution_snapshots",
                        to="lens.secretversion",
                    ),
                ),
                (
                    "invocation_id",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                (
                    "run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="plugin_execution_snapshots",
                        to="lens.run",
                    ),
                ),
                ("tool_key", models.CharField(blank=True, default="", max_length=128)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="connection",
            name="secret_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="connections",
                to="lens.secretversion",
            ),
        ),
        migrations.CreateModel(
            name="CredentialLease",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("expires_at", models.DateTimeField()),
                ("revoked_at", models.DateTimeField(blank=True, null=True)),
                (
                    "lensnode",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="credential_leases",
                        to="lens.lensnode",
                    ),
                ),
                (
                    "snapshot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="credential_leases",
                        to="lens.executionsnapshot",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="runexecution",
            name="loaded_plugins",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.CreateModel(
            name="AssistantPluginBinding",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("tools", models.JSONField(blank=True, default=list)),
                ("enabled", models.BooleanField(default=True)),
                (
                    "assistant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="plugin_bindings",
                        to="lens.assistant",
                    ),
                ),
                (
                    "connection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="assistant_bindings",
                        to="lens.connection",
                    ),
                ),
            ],
            options={
                "unique_together": {("assistant", "connection")},
            },
        ),
        migrations.AddConstraint(
            model_name="executionsnapshot",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("datasource__isnull", False),
                        ("invocation_id", ""),
                        ("kind", "datasource_sync"),
                        ("run__isnull", True),
                        ("tool_key", ""),
                    ),
                    models.Q(
                        ("datasource__isnull", True),
                        ("kind", "tool_invoke"),
                        ("run__isnull", False),
                        models.Q(("tool_key", ""), _negated=True),
                        models.Q(("invocation_id", ""), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="lens_snapshot_owner_kind_ck",
            ),
        ),
        migrations.AddConstraint(
            model_name="executionsnapshot",
            constraint=models.UniqueConstraint(
                condition=models.Q(("kind", "tool_invoke")),
                fields=("run", "invocation_id"),
                name="lens_snap_run_invocation_uniq",
            ),
        ),
        migrations.CreateModel(
            name="PluginInvocation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("datasource_sync", "Datasource Sync"),
                            ("tool_invoke", "Tool Invoke"),
                        ],
                        max_length=32,
                    ),
                ),
                ("plugin_key", models.CharField(max_length=64)),
                ("tool_key", models.CharField(blank=True, default="", max_length=128)),
                (
                    "capability",
                    models.CharField(blank=True, default="", max_length=128),
                ),
                ("resource_summary", models.JSONField(blank=True, default=dict)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("authorized", "Authorized"),
                            ("materialized", "Materialized"),
                        ],
                        default="authorized",
                        max_length=24,
                    ),
                ),
                ("materialized_at", models.DateTimeField(blank=True, null=True)),
                (
                    "actor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="plugin_invocations",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "connection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="plugin_invocations",
                        to="lens.connection",
                    ),
                ),
                (
                    "datasource",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="plugin_invocations",
                        to="lens.datasource",
                    ),
                ),
                (
                    "lensnode",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="plugin_invocations",
                        to="lens.lensnode",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="plugin_invocations",
                        to="lens.run",
                    ),
                ),
                (
                    "snapshot",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="invocation_audit",
                        to="lens.executionsnapshot",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="mcpserver",
            name="connection",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="mcp_adapters",
                to="lens.connection",
            ),
        ),
        migrations.AddField(
            model_name="mcpserver",
            name="tools",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AlterField(
            model_name="mcpserver",
            name="transport",
            field=models.CharField(
                choices=[
                    ("url", "URL"),
                    ("stdio", "STDIO"),
                    ("plugin", "Plugin Adapter"),
                ],
                max_length=16,
            ),
        ),
        migrations.CreateModel(
            name="LegacyIntegrationMigration",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "uuid",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "source_kind",
                    models.CharField(
                        choices=[
                            ("credential", "Credential"),
                            ("datasource", "Datasource"),
                        ],
                        max_length=16,
                    ),
                ),
                ("source_uuid", models.UUIDField()),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("migrated", "Migrated"),
                            ("manual_review", "Manual Review"),
                            ("rolled_back", "Rolled Back"),
                        ],
                        max_length=24,
                    ),
                ),
                ("reason", models.CharField(blank=True, default="", max_length=64)),
                ("details", models.JSONField(blank=True, default=dict)),
                (
                    "connection",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="legacy_migration_records",
                        to="lens.connection",
                    ),
                ),
                (
                    "datasource",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="legacy_migration_records",
                        to="lens.datasource",
                    ),
                ),
            ],
            options={
                "ordering": ["source_kind", "source_uuid"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("source_kind", "source_uuid"),
                        name="lens_legacy_migration_source_uniq",
                    )
                ],
            },
        ),
        migrations.AlterField(
            model_name="datasource",
            name="source_type",
            field=models.CharField(
                choices=[
                    ("git", "Git"),
                    ("feishu", "Feishu"),
                    ("jira", "Jira"),
                    ("managed_workspace", "Managed Workspace"),
                ],
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name="assistant",
            name="routing_mode",
            field=models.CharField(
                choices=[("direct", "Standard Mode"), ("smart", "Smart Collaboration")],
                db_index=True,
                default="direct",
                max_length=16,
            ),
        ),
        migrations.RunPython(
            bind_token_budget_to_agent_rounds,
            migrations.RunPython.noop,
        ),
        migrations.RunPython(
            bootstrap_plugin_releases,
            migrations.RunPython.noop,
        ),
    ]
