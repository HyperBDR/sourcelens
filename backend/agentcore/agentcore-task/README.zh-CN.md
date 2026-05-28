# Agentcore Task

[English](README.md)

面向 Django + Celery 项目的统一任务执行记录与查询模块。

- **旁路记录**：记录每次任务执行（谁、何时、状态、结果、错误），不驱动工作流或重试。
- **实时更新**：任务运行中或从 Celery 同步更新状态、result/error/traceback；**进度**可写入 `TaskExecution.metadata`（见后端使用中的 **推荐在 metadata 中使用的字段（进度）**）。
- **异常与超时**：可存储失败原因（如超时）；超时/撤销逻辑由业务或监控侧实现。
- **任务锁**：防止重复执行（acquire/release、`@prevent_duplicate_task`）。
- REST API：列表、筛选、同步任务执行。

设计说明：[docs/DESIGN.md](docs/DESIGN.md)。设计结论摘要：[docs/DESIGN_SUMMARY.md](docs/DESIGN_SUMMARY.md)。提交前审查（ray-code-standards）：[docs/PRE_COMMIT_REVIEW.md](docs/PRE_COMMIT_REVIEW.md)。

---

## 数据库

**推荐 PostgreSQL。**  
任务详情存放在 JSON 字段（`task_args`、`task_kwargs`、`result`、`metadata`）。Django `JSONField` 在 PostgreSQL、MySQL、SQLite 上均可用，但 **JSONB 及 JSONB 索引**（如对 `metadata`/`result` 做 GIN 查询）**仅 PostgreSQL 支持**。若后续需按这些字段内容筛选或建索引，请使用 PostgreSQL。锁使用 Django 缓存后端（Redis、数据库等），与 DB 选择无关。

---

## 安装

- **未上架 PyPI**，仅支持从 GitHub 安装。

**从 GitHub 安装**（克隆后可编辑）：
```bash
pip install -e git+https://github.com/cloud2ai/agentcore-task.git
```
若主项目以 submodule 方式引用，在仓库根目录执行：
```bash
pip install -e path/to/agentcore-task
```
- 主项目 Dockerfile 需遍历 `agentcore/` 下各子模块并执行 `pip install -e`。
- 详细说明见主项目 README。

---

## 后端使用

1. **注册**
   - 在 `INSTALLED_APPS` 中加入 `'agentcore_task.adapters.django'`
   - 在根 URLconf 中加入 `path('api/v1/tasks/', include('agentcore_task.adapters.django.urls'))`

   **定时任务（Beat）**

   > **使用本模块时请注意：** 本模块的两个定时任务会在启动时**自动合并到 Celery Beat 调度**中，**由 Beat 按配置时间自动执行**。无需在您的项目中再次注册。若希望这些任务被执行，请确保已运行 Celery Beat。

   只要把本 app 加入 `INSTALLED_APPS`，`AppConfig.ready()` 就会将上述两条合并进 `settings.CELERY_BEAT_SCHEDULE`（可通过配置关闭）。若主项目使用 django_celery_beat 的 DatabaseScheduler，需在 Celery 加载时将 `CELERY_BEAT_SCHEDULE` 同步到数据库（与 core/settings/celery.py 中手写条目一致），这样各 app 合并的条目也会被调度。两个任务分别为：

   | 任务 | 作用 | 默认执行时间 | 启用 / 调度配置 |
   |------|------|----------------|------------------|
   | **清理** | 删除过期的 `TaskExecution` 记录，控制库表体积 | 每天 02:00（crontab `0 2 * * *`） | `AGENTCORE_TASK_CLEANUP_ENABLED`（默认 True）。调度：`AGENTCORE_TASK_CLEANUP_CRONTAB`；解析失败时用 `AGENTCORE_TASK_CLEANUP_BEAT_INTERVAL_HOURS`（24）作为间隔 |
   | **超时标记** | 将超过时限仍为 `STARTED` 的执行标记为 `FAILURE` | 每 30 分钟（`*/30 * * * *`） | `AGENTCORE_TASK_MARK_TIMEOUT_ENABLED`（默认 True）。调度：`AGENTCORE_TASK_MARK_TIMEOUT_CRONTAB` |

   **清理任务** — `agentcore_task.adapters.django.tasks.cleanup_old_task_executions`

   | 项 | 值 |
   |----|-----|
   | Beat 调度键 | `agentcore-task-cleanup-old-executions` |
   | 默认执行时间 | 每天 02:00（crontab `0 2 * * *`） |
   | 任务参数（Beat 调用时） | 不传，使用下面配置 |
   | 实际行为 | 使用 `AGENTCORE_TASK_RETENTION_DAYS`（默认 30）、`AGENTCORE_TASK_CLEANUP_ONLY_COMPLETED`（默认 True）。手动调用时可传 `retention_days`、`only_completed`。当 `AGENTCORE_TASK_CLEANUP_ENABLED` 为 False 时不执行。 |

   **超时标记任务** — `agentcore_task.adapters.django.tasks.mark_timed_out_task_executions`

   | 项 | 值 |
   |----|-----|
   | Beat 调度键 | `agentcore-task-mark-timed-out-executions` |
   | 默认执行时间 | 每 30 分钟（`*/30 * * * *`） |
   | 任务参数（Beat 调用时） | 不传，使用下面配置 |
   | 实际行为 | 先从 Celery 同步未结束执行，再将超过 `AGENTCORE_TASK_TIMEOUT_MINUTES`（默认 10）仍为 `STARTED` 的标记为 `FAILURE`。手动调用时可传 `timeout_minutes`。当 `AGENTCORE_TASK_MARK_TIMEOUT_ENABLED` 为 False 时不执行。 |

2. **创建与更新任务记录**（按时序）

   **`register_task_execution`** — 参数：

   | 参数           | 类型   | 必填 | 说明 |
   |----------------|--------|------|------|
   | `task_id`      | str    | 是   | Celery 任务 id（如 `task.delay(...)` 返回的 `task.id`） |
   | `task_name`    | str    | 是   | 任务名（如 `'myapp.tasks.my_task'`） |
   | `module`       | str    | 是   | 模块/业务范围（如 `'myapp'`） |
   | `task_args`    | list   | 否   | 传给任务的位置参数（以 JSON 存储） |
   | `task_kwargs`  | dict   | 否   | 传给任务的关键字参数（以 JSON 存储） |
   | `created_by`   | User   | 否   | 触发用户；系统/定时任务可不传 |
   | `metadata`     | dict   | 否   | 额外上下文（如 `{"source": "manual_trigger"}`） |
   | `initial_status` | str  | 否   | 定时任务可设为 `TaskStatus.STARTED`（一次调用完成登记） |

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

   **更新**状态与进度：在任务内部在开始、结束或汇报进度时调用 `TaskTracker.update_task_status(...)`。

   **`TaskTracker.update_task_status`** — 参数：

   | 参数       | 类型 | 必填 | 说明 |
   |------------|------|------|------|
   | `task_id`  | str  | 是   | Celery 任务 id |
   | `status`   | str  | 是   | 取值见下 `TaskStatus` |
   | `result`   | any  | 否   | 结果负载（以 JSON 存储）；SUCCESS 时使用 |
   | `error`    | str  | 否   | 错误信息；FAILURE 时使用 |
   | `traceback`| str  | 否   | 堆栈文本；FAILURE 时使用 |
   | `metadata` | dict | 否   | 会**合并**到现有 `TaskExecution.metadata`，不整体替换 |

   **状态取值**（`TaskStatus`）：`PENDING`、`STARTED`、`SUCCESS`、`FAILURE`、`RETRY`、`REVOKED`。终态：`SUCCESS`、`FAILURE`、`REVOKED`。

   ```python
   def my_task(...):
       TaskTracker.update_task_status(
           task_id, TaskStatus.STARTED, metadata={"progress_percent": 0}
       )
       # ... 业务逻辑 ...
       TaskTracker.update_task_status(
           task_id, TaskStatus.SUCCESS, result={"count": 1}
       )
   ```

   **推荐在 `metadata` 中使用的字段（进度）** — 面向用户的进度（如「解析中… 30%」）请写入 `metadata`；模块会**合并**键值且不替换整个对象。以下键便于前端统一展示「步骤 X：文案 (Y%)」：

   | 键                 | 类型 | 说明 |
   |--------------------|------|------|
   | `progress_percent` | int  | 0–100，整体进度 |
   | `progress_message` | str  | 当前步骤简短文案（如 "Parsing…"、"Saving…"） |
   | `progress_step`    | str  | 步骤标识（如 `prepare`、`interpret`、`finalize`） |

   每个关键步骤传入上述键即可；可额外增加业务键（如业务记录链接）。日志/步骤列表由业务按需用于调试或审计。

3. **任务锁（可选）**  
   使用 `@prevent_duplicate_task` 避免同一任务（或同一参数）重复执行。

   **`@prevent_duplicate_task`** — 参数：

   | 参数        | 类型 | 默认   | 说明 |
   |-------------|------|--------|------|
   | `lock_name` | str  | —      | 锁键（如任务名） |
   | `timeout`   | int  | 3600   | 锁 TTL（秒）；应 ≥ 单次任务典型执行时间 |
   | `lock_param`| str  | None   | 若设置，锁按该 kwarg 区分（如 `"user_id"` 表示按用户一把锁） |

   当任务已在运行或加锁失败时，装饰器直接返回一个 dict（如 `{"success": False, "status": "skipped", "reason": "task_already_running"}`），不执行任务体。

   ```python
   from agentcore_task.adapters.django import prevent_duplicate_task

   @shared_task(name="myapp.tasks.my_task")
   @prevent_duplicate_task("my_task", lock_param="user_id", timeout=3600)
   def my_task(user_id):
       ...
   ```

4. **其他导出**（从 `agentcore_task.adapters.django` 导入，实现在 `.services`）：
   - **锁**：`acquire_task_lock`、`release_task_lock`、`is_task_locked`、`prevent_duplicate_task`
   - **记录与查询**：`TaskTracker`、`register_task_execution`、`TaskStatus`、`TaskLogCollector`
   - 使用 `from agentcore_task.adapters.django import ...`；可选 `from agentcore_task.adapters.django.services import ...`（符号相同）。

---

## 清理与全局配置

**与定时任务、清理相关的 Django 配置**（均为可选）：

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `AGENTCORE_TASK_CLEANUP_ENABLED` | bool | True | False 时清理定时任务不执行且不加入 Beat |
| `AGENTCORE_TASK_CLEANUP_CRONTAB` | str | `"0 2 * * *"` | 5 段 cron：清理任务执行时间（默认每天 02:00） |
| `AGENTCORE_TASK_CLEANUP_BEAT_INTERVAL_HOURS` | int | 24 | crontab 解析失败时的 fallback 间隔（小时） |
| `AGENTCORE_TASK_RETENTION_DAYS` | int | 30 | 删除早于该天数的执行记录 |
| `AGENTCORE_TASK_CLEANUP_ONLY_COMPLETED` | bool | True | True 时仅删除 SUCCESS/FAILURE/REVOKED；False 时含 PENDING/STARTED/RETRY |
| `AGENTCORE_TASK_MARK_TIMEOUT_ENABLED` | bool | True | False 时超时标记定时任务不执行且不加入 Beat |
| `AGENTCORE_TASK_MARK_TIMEOUT_CRONTAB` | str | `"*/30 * * * *"` | 5 段 cron：超时标记任务执行间隔（默认每 30 分钟） |
| `AGENTCORE_TASK_TIMEOUT_MINUTES` | int | 10 | 超过该分钟数仍为 STARTED 的执行将被标记为 FAILURE |

- **手动清理**：从 `agentcore_task.adapters.django` 调用 `cleanup_old_executions(retention_days=..., only_completed=...)`。参数：`retention_days`（int，可选）、`only_completed`（bool，可选）。
- **自定义调度**：Beat 条目在 `ready()` 中自动合并。若需自定义，可在 app 加载前在 settings 中设置 `CELERY_BEAT_SCHEDULE`，或在加载后自行合并 `get_cleanup_beat_schedule(interval_hours=12)` / `get_mark_timeout_beat_schedule()`。

---

## API 参考

- 基础路径：`api/v1/tasks/`（通过根 URLconf 挂载）。
- **鉴权**：与主项目一致（如 session、token）。列表/详情支持按 `created_by`、`my_tasks` 做范围过滤。

### 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `.../executions/` | 列表（分页），查询参数见下 |
| GET | `.../executions/my-tasks/` | 当前用户任务列表（分页），查询参数同列表（`created_by` 固定为当前用户） |
| GET | `.../executions/{id}/` | 按主键 `id` 详情 |
| GET | `.../executions/by-task-id/{task_id}/` | 按 Celery `task_id` 查询 |
| GET | `.../executions/status/` | 按 `task_id` 查状态；可选是否从 Celery 同步 |
| POST | `.../executions/{id}/sync/` | 从 Celery 同步状态/结果/错误到 DB |
| GET | `.../executions/stats/` | 按状态、按 module/task_name 汇总统计 |

### GET `.../executions/` — 列表

查询参数（均为可选）：

| 参数 | 类型 | 说明 |
|------|------|------|
| `module` | string | 按 `module` 筛选 |
| `task_name` | string | 按 `task_name` 筛选 |
| `status` | string | 按状态筛选（`PENDING`、`STARTED`、`SUCCESS`、`FAILURE`、`RETRY`、`REVOKED`） |
| `created_by` | int | 用户 id，按创建人筛选。未传且未设 `my_tasks` 时列表默认当前用户 |
| `my_tasks` | string | 设为 `"false"` 表示不看当前用户范围（受权限约束）；不传或其它值时与 `created_by` 未传等价为当前用户 |
| `start_date` | string | `created_at >= start_date`（ISO 或日期） |
| `end_date` | string | `created_at <= end_date` |
| `page` | int | 页码（若项目开启分页） |
| `page_size` | int | 每页条数（若项目支持） |

响应（列表）：对象数组，含 `id`、`task_id`、`task_name`、`module`、`status`、`created_at`、`started_at`、`finished_at`、`created_by_id`、`created_by_username`、`duration`、`is_completed`、`is_running`。

### GET `.../executions/{id}/` 及按 task_id 详情

响应字段：`id`、`task_id`、`task_name`、`module`、`status`、`created_at`、`started_at`、`finished_at`、`task_args`、`task_kwargs`、`result`、`error`、`traceback`、`created_by`、`created_by_id`、`created_by_username`、`metadata`、`duration`、`is_completed`、`is_running`。

### GET `.../executions/status/`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | string | 是 | Celery 任务 id |
| `sync` | string | 否 | 默认 `"true"` 表示先从 Celery 同步再返回；`"false"` 仅返回 DB 中的状态 |

响应格式同详情。未找到返回 404。

### GET `.../executions/stats/`

查询参数（均为可选）：`module`、`task_name`、`created_by`（用户 id）、`my_tasks`（语义同列表）。

响应（200）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `total` | int | 总条数 |
| `pending`、`started`、`success`、`failure`、`retry`、`revoked` | int | 各状态数量 |
| `by_module` | object | `{ "<module>": { "total", "pending", "started", "success", "failure", "retry", "revoked" } }` |
| `by_task_name` | object | `{ "<task_name>": { 同上 } }` |
