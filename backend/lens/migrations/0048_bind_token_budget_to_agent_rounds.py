from django.db import migrations


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


class Migration(migrations.Migration):
    dependencies = [
        ("lens", "0047_plugin_integrations"),
    ]

    operations = [
        migrations.RunPython(
            bind_token_budget_to_agent_rounds,
            migrations.RunPython.noop,
        ),
    ]
