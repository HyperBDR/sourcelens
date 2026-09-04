from django.db import migrations, models


def populate_content_languages(apps, schema_editor):
    """Recover the language for shares created before this field existed."""

    SharedQA = apps.get_model("lens", "SharedQA")
    for share in SharedQA.objects.select_related("run__execution").filter(
        content_language=""
    ):
        snapshot = getattr(
            getattr(share.run, "execution", None),
            "runtime_snapshot",
            {},
        ) or {}
        value = snapshot.get("answer_language")
        normalized = str(value or "").strip().replace("_", "-").lower()
        prefix = normalized.split("-", 1)[0]
        language = {"en": "en-US", "zh": "zh-CN", "es": "es"}.get(
            prefix, ""
        )
        if language:
            share.content_language = language
            share.save(update_fields=["content_language"])


class Migration(migrations.Migration):
    dependencies = [("lens", "0046_assistant_fixed_collaboration")]

    operations = [
        migrations.AddField(
            model_name="sharedqa",
            name="content_language",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Language used by the generated Q&A content.",
                max_length=16,
            ),
        ),
        migrations.RunPython(
            populate_content_languages,
            migrations.RunPython.noop,
        ),
        migrations.RemoveIndex(
            model_name="sharedqa",
            name="lens_sharedqa_list_idx",
        ),
        migrations.AddIndex(
            model_name="sharedqa",
            index=models.Index(
                fields=[
                    "assistant",
                    "content_language",
                    "is_listed",
                    "status",
                    "-published_at",
                ],
                name="lens_sharedqa_list_idx",
            ),
        ),
    ]
