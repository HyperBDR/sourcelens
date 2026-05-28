# Agentcore Task

[中文](README.zh-CN.md)

Unified task execution module for Django projects with Celery.

- **Side-channel recording**: records each task run (who, when, status, result, error) without driving workflow or retry.
- **Real-time update**: status and result/error/traceback updated as the task runs or from Celery; **progress** can be reported in `TaskExecution.metadata` (see **Recommended fields in metadata (progress)** in Backend usage).
- **Common exception handling**: store failure reasons (e.g. timeout); timeout/revoke logic stays in business or monitor code.
- **Task lock**: prevent duplicate execution (acquire/release, `@prevent_duplicate_task`).
- REST API for listing, filtering, and syncing task executions.

Design rationale: [docs/DESIGN.md](docs/DESIGN.md). **设计结论摘要**（中文）：[docs/DESIGN_SUMMARY.md](docs/DESIGN_SUMMARY.md). **提交前审查**：使用 ray-code-standards，见 [docs/PRE_COMMIT_REVIEW.md](docs/PRE_COMMIT_REVIEW.md).

---

## Database

**Recommended: PostgreSQL.**  
Task execution details are stored in JSON fields (`task_args`, `task_kwargs`, `result`, `metadata`). Django’s `JSONField` is supported on PostgreSQL, MySQL, and SQLite, but **JSONB and JSONB indexes** (e.g. GIN for querying inside `metadata`/`result`) are **PostgreSQL-only**. If you need to filter or index by content inside those fields later, use PostgreSQL. The lock uses the Django cache backend (Redis, database, etc.), independent of the DB choice.

---

## Install

- **Not on PyPI**, install only from GitHub.

**From GitHub** (editable after clone):
```bash
pip install -e git+https://github.com/cloud2ai/agentcore-task.git
```
Or, when the host project uses it as a submodule, from repo root:
```bash
pip install -e path/to/agentcore-task
```
- The host project Dockerfile should iterate over `agentcore/`
  submodules and run `pip install -e`.
- See the host project README for details.

---

## Backend: usage

1. **Register**
   - Add `'agentcore_task.adapters.django'` to `INSTALLED_APPS`
   - Add `path('api/v1/tasks/', include('agentcore_task.adapters.django.urls'))` to root URLconf

   **Scheduled tasks (Beat)**

   > **Important for users:** The module’s two scheduled tasks are **automatically merged into the Celery Beat schedule** at startup and **run by Beat at the configured times**. You do not need to register them in your project. Ensure Celery Beat is running if you want these tasks to execute.

   Once the app is in `INSTALLED_APPS`, `AppConfig.ready()` merges the two entries into `settings.CELERY_BEAT_SCHEDULE` (unless disabled). If the host project uses django_celery_beat's DatabaseScheduler, it should sync `CELERY_BEAT_SCHEDULE` to the database when Celery loads (same as entries defined in core/settings/celery.py), so that merged entries from apps are also scheduled. They are:

   | Task | Purpose | Default schedule | Enable / schedule settings |
   |------|---------|------------------|----------------------------|
   | **Cleanup** | Delete old `TaskExecution` rows to cap DB size | Daily at 02:00 (`0 2 * * *`) | `AGENTCORE_TASK_CLEANUP_ENABLED` (default True). Schedule: `AGENTCORE_TASK_CLEANUP_CRONTAB`; fallback interval: `AGENTCORE_TASK_CLEANUP_BEAT_INTERVAL_HOURS` (24) |
   | **Mark timeout** | Mark `STARTED` runs older than timeout as `FAILURE` | Every 30 minutes (`*/30 * * * *`) | `AGENTCORE_TASK_MARK_TIMEOUT_ENABLED` (default True). Schedule: `AGENTCORE_TASK_MARK_TIMEOUT_CRONTAB` |

   **Cleanup task** — `agentcore_task.adapters.django.tasks.cleanup_old_task_executions`

   | Item | Value |
   |------|--------|
   | Beat schedule key | `agentcore-task-cleanup-old-executions` |
   | Default run time | 02:00 every day (crontab `0 2 * * *`) |
   | Task parameters (passed by Beat) | None (uses config below when omitted) |
   | Effective behavior | Uses `AGENTCORE_TASK_RETENTION_DAYS` (default 30), `AGENTCORE_TASK_CLEANUP_ONLY_COMPLETED` (default True). If you call the task manually you can pass `retention_days`, `only_completed`. No-op when `AGENTCORE_TASK_CLEANUP_ENABLED` is False. |

   **Mark-timeout task** — `agentcore_task.adapters.django.tasks.mark_timed_out_task_executions`

   | Item | Value |
   |------|--------|
   | Beat schedule key | `agentcore-task-mark-timed-out-executions` |
   | Default run time | Every 30 minutes (`*/30 * * * *`) |
   | Task parameters (passed by Beat) | None (uses config below when omitted) |
   | Effective behavior | Syncs unfinished runs from Celery, then marks `STARTED` tasks older than `AGENTCORE_TASK_TIMEOUT_MINUTES` (default 10) as `FAILURE`. If you call the task manually you can pass `timeout_minutes`. No-op when `AGENTCORE_TASK_MARK_TIMEOUT_ENABLED` is False. |

2. **Create and update task records** (in order)

   **Create** a task execution record right after dispatching the Celery task so the run appears in list/detail and can receive status updates. Pass `created_by` when a user triggered the task (e.g. from a request); omit for system/scheduled tasks.

   **`register_task_execution`** — parameters:

   | Parameter        | Type   | Required | Description |
   |------------------|--------|----------|-------------|
   | `task_id`        | str    | yes      | Celery task id (e.g. `task.id` from `task.delay(...)`) |
   | `task_name`      | str    | yes      | Task name (e.g. `'myapp.tasks.my_task'`) |
   | `module`         | str    | yes      | Module/business scope (e.g. `'myapp'`) |
   | `task_args`      | list   | no       | Positional args passed to the task (stored as JSON) |
   | `task_kwargs`    | dict   | no       | Keyword args passed to the task (stored as JSON) |
   | `created_by`     | User   | no       | User who triggered; omit for system/scheduled tasks |
   | `metadata`       | dict   | no       | Extra context (e.g. `{"source": "manual_trigger"}`) |
   | `initial_status` | str    | no       | Set to `TaskStatus.STARTED` for periodic tasks (one-shot registration) |

   ```python
   from agentcore_task.adapters.django import (
       register_task_execution,
       TaskTracker,
       TaskStatus,
   )

   task = my_celery_task.delay(...)
   register_task_execution(
       task_id=task.id,
       task_name="myapp.tasks.my_task",
       module="myapp",
       task_kwargs={...},
       created_by=request.user,
       metadata={"source": "manual_trigger"},
   )
   ```

   **Update** status and progress from inside the task. Call `TaskTracker.update_task_status(...)` when the task starts, finishes, or reports progress.

   **`TaskTracker.update_task_status`** — parameters:

   | Parameter  | Type | Required | Description |
   |------------|------|----------|-------------|
   | `task_id`  | str  | yes      | Celery task id |
   | `status`   | str  | yes      | One of `TaskStatus` (see below) |
   | `result`   | any  | no       | Result payload (stored as JSON); use on SUCCESS |
   | `error`    | str  | no       | Error message; use on FAILURE |
   | `traceback`| str  | no       | Traceback text; use on FAILURE |
   | `metadata`| dict | no       | Merged into existing `TaskExecution.metadata` (not replaced) |

   **Status values** (`TaskStatus`): `PENDING`, `STARTED`, `SUCCESS`, `FAILURE`, `RETRY`, `REVOKED`. Completed: `SUCCESS`, `FAILURE`, `REVOKED`.

   ```python
   def my_task(...):
       TaskTracker.update_task_status(
           task_id, TaskStatus.STARTED, metadata={"progress_percent": 0}
       )
       # ... work ...
       TaskTracker.update_task_status(
           task_id, TaskStatus.SUCCESS, result={"count": 1}
       )
   ```

   **Recommended fields in `metadata` (progress)** — for user-facing progress (e.g. "Parsing… 30%"), put them in `metadata`; the module **merges** keys and does not replace the whole object. Use these keys so UIs can show "Step X: message (Y%)" consistently:

   | Key                 | Type | Description |
   |---------------------|------|-------------|
   | `progress_percent`  | int  | 0–100, overall progress |
   | `progress_message`  | str  | Short message for current step (e.g. "Parsing…", "Saving…") |
   | `progress_step`     | str  | Step id (e.g. `prepare`, `interpret`, `finalize`) |

   On each meaningful step, pass these in `metadata`; you can add more keys (e.g. link to a business record). Logs/step lists are up to the module for debugging or audit.

3. **Task lock (optional)**  
   Use `@prevent_duplicate_task` to avoid overlapping runs of the same (param) task.

   **`@prevent_duplicate_task`** — arguments:

   | Argument     | Type | Default | Description |
   |--------------|------|---------|-------------|
   | `lock_name`  | str  | —       | Lock key (e.g. task name) |
   | `timeout`   | int  | 3600    | Lock TTL in seconds; should be ≥ typical run duration |
   | `lock_param`| str  | None    | If set, lock is scoped by this kwarg (e.g. `"user_id"` → one lock per user) |

   When the task is already running or lock acquisition fails, the decorator returns a dict (e.g. `{"success": False, "status": "skipped", "reason": "task_already_running"}`) and does not run the task body.

   ```python
   from agentcore_task.adapters.django import prevent_duplicate_task

   @shared_task(name="myapp.tasks.my_task")
   @prevent_duplicate_task("my_task", lock_param="user_id", timeout=3600)
   def my_task(user_id):
       ...
   ```

4. **Other exports** (from `agentcore_task.adapters.django`, implemented in `.services`):
   - **Lock**: `acquire_task_lock`, `release_task_lock`, `is_task_locked`, `prevent_duplicate_task`
   - **Recording**: `TaskTracker`, `register_task_execution`, `TaskStatus`, `TaskLogCollector`
   - Use `from agentcore_task.adapters.django import ...`; optional `from agentcore_task.adapters.django.services import ...` (same symbols).

---

## Cleanup and global config

**Django settings** that affect scheduled tasks and cleanup (all optional):

| Setting | Type | Default | Description |
|---------|------|---------|-------------|
| `AGENTCORE_TASK_CLEANUP_ENABLED` | bool | True | If False, cleanup Beat task is no-op and not added to schedule |
| `AGENTCORE_TASK_CLEANUP_CRONTAB` | str | `"0 2 * * *"` | 5-field cron: cleanup run time (default daily 02:00) |
| `AGENTCORE_TASK_CLEANUP_BEAT_INTERVAL_HOURS` | int | 24 | Fallback interval (hours) if crontab is invalid |
| `AGENTCORE_TASK_RETENTION_DAYS` | int | 30 | Delete executions older than this many days |
| `AGENTCORE_TASK_CLEANUP_ONLY_COMPLETED` | bool | True | If True, only delete SUCCESS/FAILURE/REVOKED; if False, also PENDING/STARTED/RETRY |
| `AGENTCORE_TASK_MARK_TIMEOUT_ENABLED` | bool | True | If False, mark-timeout Beat task is no-op and not added to schedule |
| `AGENTCORE_TASK_MARK_TIMEOUT_CRONTAB` | str | `"*/30 * * * *"` | 5-field cron: mark-timeout run interval (default every 30 min) |
| `AGENTCORE_TASK_TIMEOUT_MINUTES` | int | 10 | Treat STARTED tasks older than this (minutes) as FAILURE |

- **Manual cleanup**: `cleanup_old_executions(retention_days=..., only_completed=...)` from `agentcore_task.adapters.django`. Params: `retention_days` (int, optional), `only_completed` (bool, optional).
- **Override schedule**: Beat entries are auto-merged in `ready()`. To customize, set `CELERY_BEAT_SCHEDULE` in your settings **before** the app loads, or after load merge in `get_cleanup_beat_schedule(interval_hours=12)` / `get_mark_timeout_beat_schedule()` yourself.

---

## API reference

- Base path: `api/v1/tasks/` (mount via root URLconf).
- **Auth**: same as the host project (e.g. session, token). List/detail respect `created_by` and `my_tasks` for scoping.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `.../executions/` | List executions (paginated). Query params below. |
| GET | `.../executions/my-tasks/` | List current user's executions (paginated). Same query params as list (except `created_by` fixed to current user). |
| GET | `.../executions/{id}/` | Detail by primary key `id`. |
| GET | `.../executions/by-task-id/{task_id}/` | Lookup by Celery `task_id`. |
| GET | `.../executions/status/` | Status by `task_id`; optional sync from Celery. |
| POST | `.../executions/{id}/sync/` | Sync status/result/error from Celery into DB. |
| GET | `.../executions/stats/` | Aggregate counts by status and by module/task_name. |

### GET `.../executions/` — list

Query params (all optional):

| Param | Type | Description |
|-------|------|-------------|
| `module` | string | Filter by `module`. |
| `task_name` | string | Filter by `task_name`. |
| `status` | string | Filter by status (`PENDING`, `STARTED`, `SUCCESS`, `FAILURE`, `RETRY`, `REVOKED`). |
| `created_by` | int | User id; filter by creator. If omitted and `my_tasks` not set, list defaults to current user. |
| `my_tasks` | string | `"false"` to list all (subject to permissions); omit or other to scope by current user when `created_by` also omitted. |
| `start_date` | string | Filter `created_at >= start_date` (ISO or date). |
| `end_date` | string | Filter `created_at <= end_date`. |
| `page` | int | Page number (if pagination enabled). |
| `page_size` | int | Page size (if project supports it). |

Response (list): array of objects with `id`, `task_id`, `task_name`, `module`, `status`, `created_at`, `started_at`, `finished_at`, `created_by_id`, `created_by_username`, `duration`, `is_completed`, `is_running`.

### GET `.../executions/{id}/` and detail by task_id

Response fields: `id`, `task_id`, `task_name`, `module`, `status`, `created_at`, `started_at`, `finished_at`, `task_args`, `task_kwargs`, `result`, `error`, `traceback`, `created_by`, `created_by_id`, `created_by_username`, `metadata`, `duration`, `is_completed`, `is_running`.

### GET `.../executions/status/`

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | string | yes | Celery task id. |
| `sync` | string | no | `"true"` (default) to sync from Celery before returning; `"false"` to return DB only. |

Response: same shape as detail. 404 if not found.

### GET `.../executions/stats/`

Query params (all optional): `module`, `task_name`, `created_by` (user id), `my_tasks` (same semantics as list).

Response (200):

| Field | Type | Description |
|-------|------|-------------|
| `total` | int | Total count. |
| `pending`, `started`, `success`, `failure`, `retry`, `revoked` | int | Count per status. |
| `by_module` | object | `{ "<module>": { "total", "pending", "started", "success", "failure", "retry", "revoked" } }`. |
| `by_task_name` | object | `{ "<task_name>": { same counts } }`. |
