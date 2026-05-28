"""
Task execution tracking models for unified task management.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from agentcore_task.constants import TaskStatus


class TaskExecution(models.Model):
    """
    Unified task execution record model.
    Tracks Celery task executions across modules.
    """

    STATUS_CHOICES = [
        (TaskStatus.PENDING, "Pending"),
        (TaskStatus.STARTED, "Started"),
        (TaskStatus.SUCCESS, "Success"),
        (TaskStatus.FAILURE, "Failure"),
        (TaskStatus.RETRY, "Retry"),
        (TaskStatus.REVOKED, "Revoked"),
    ]

    task_id = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Celery task ID",
    )
    task_name = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Task name (e.g. cloud_billing.tasks.collect_billing_data)",
    )
    module = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Module that owns this task (e.g. cloud_billing)",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=TaskStatus.PENDING,
        db_index=True,
        help_text="Current task status",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When the task was created",
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the task started execution",
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the task finished execution",
    )
    task_args = models.JSONField(
        null=True,
        blank=True,
        help_text="Task arguments",
    )
    task_kwargs = models.JSONField(
        null=True,
        blank=True,
        help_text="Task keyword arguments",
    )
    result = models.JSONField(
        null=True,
        blank=True,
        help_text="Task result data",
    )
    error = models.TextField(
        null=True,
        blank=True,
        help_text="Error message if task failed",
    )
    traceback = models.TextField(
        null=True,
        blank=True,
        help_text="Error traceback if task failed",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_tasks",
        help_text="User who triggered this task",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional metadata for the task",
    )

    class Meta:
        db_table = "agentcore_task_execution"
        verbose_name = "Task Execution"
        verbose_name_plural = "Task Executions"
        indexes = [
            models.Index(fields=["module", "status"]),
            models.Index(fields=["task_name", "status"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["module", "created_at"]),
            models.Index(fields=["created_by", "status"]),
            models.Index(fields=["created_by", "created_at"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.task_name} ({self.task_id}) - {self.status}"

    @property
    def duration(self):
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()

        if self.started_at:
            return (timezone.now() - self.started_at).total_seconds()

        return None

    @property
    def is_completed(self):
        return self.status in TaskStatus.get_completed_statuses()

    @property
    def is_running(self):
        return self.status in TaskStatus.get_running_statuses()

    @classmethod
    def get_user_tasks(cls, user, **filters):
        queryset = cls.objects.filter(created_by=user)
        if filters:
            queryset = queryset.filter(**filters)
        return queryset


class TaskConfig(models.Model):
    """
    Task module config: global and optional user-level.
    For now only global keys (e.g. retention_days) are used; user_id
    is reserved for future per-user overrides.
    """
    SCOPE_GLOBAL = "global"
    SCOPE_USER = "user"
    SCOPE_CHOICES = [(SCOPE_GLOBAL, "Global"), (SCOPE_USER, "User")]

    scope = models.CharField(
        max_length=20,
        choices=SCOPE_CHOICES,
        default=SCOPE_GLOBAL,
        db_index=True,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
        help_text="Null for global scope; set for user-level override.",
    )
    key = models.CharField(max_length=128, db_index=True)
    value = models.JSONField(
        default=dict,
        help_text="Config payload, e.g. {\"retention_days\": 30}.",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "agentcore_task_config"
        verbose_name = "Task Config"
        verbose_name_plural = "Task Configs"
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "user", "key"],
                name="agentcore_task_config_scope_user_key_uniq",
            )
        ]
        indexes = [models.Index(fields=["scope", "key"])]

    def __str__(self):
        u = f"user={self.user_id}" if self.user_id else "global"
        return f"TaskConfig({self.scope},{u},key={self.key})"
