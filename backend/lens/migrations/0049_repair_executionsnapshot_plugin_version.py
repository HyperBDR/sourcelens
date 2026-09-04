from django.db import migrations

PLUGIN_VERSION = "1.0.0"


def restore_plugin_version(apps, schema_editor):
    """Restore the version column removed by an unpublished migration."""

    snapshot_model = apps.get_model("lens", "ExecutionSnapshot")
    table_name = snapshot_model._meta.db_table
    introspection = schema_editor.connection.introspection
    with schema_editor.connection.cursor() as cursor:
        columns = {
            column.name
            for column in introspection.get_table_description(
                cursor,
                table_name,
            )
        }
    if "plugin_version" in columns:
        return

    field = snapshot_model._meta.get_field("plugin_version")
    original_default = field.default
    field.default = PLUGIN_VERSION
    try:
        schema_editor.add_field(snapshot_model, field)
    finally:
        field.default = original_default


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0048_bind_token_budget_to_agent_rounds"),
    ]

    operations = [
        migrations.RunPython(
            restore_plugin_version,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
