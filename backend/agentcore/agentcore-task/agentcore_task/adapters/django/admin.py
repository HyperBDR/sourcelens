"""Admin for task execution and task config (agentcore_task Django adapter)."""
from django.contrib import admin

from agentcore_task.adapters.django.models import TaskConfig, TaskExecution


@admin.register(TaskExecution)
class TaskExecutionAdmin(admin.ModelAdmin):
    list_display = [
        "task_id",
        "task_name",
        "module",
        "status",
        "created_by",
        "created_at",
        "started_at",
        "finished_at",
    ]
    list_filter = ["module", "status", "created_at"]
    search_fields = ["task_id", "task_name", "module"]
    readonly_fields = ["task_id", "created_at", "started_at", "finished_at"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]


@admin.register(TaskConfig)
class TaskConfigAdmin(admin.ModelAdmin):
    list_display = ["scope", "user", "key", "value", "updated_at"]
    list_filter = ["scope", "key"]
    search_fields = ["key"]
    raw_id_fields = ["user"]
    ordering = ["scope", "key"]
