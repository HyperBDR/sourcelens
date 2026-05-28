# Design Principles

## Side-channel recording (旁路记录)

Task execution is **side-channel recording**: we record what happens when a task runs. The tracker does not drive the workflow or own retry semantics.

- Long-running tasks need a **durable, queryable record** of each run (who, when, status, result, error).
- This record is **alongside** the actual work; the business logic and Celery remain the source of truth for execution and scheduling.
- The abstraction only provides: **record once per run**, **update in real time**, and **common exception handling** (e.g. timeout). No more.

## Retry is a business concern (业务层重试)

**Retry belongs to the business layer**, not to the task tracker.

- "Task retry" as a first-class concept in the tracker was a design mistake in earlier projects (e.g. Newshub/Devify): it mixed **recording** with **control flow**.
- Correct model: the **business object** (e.g. order, interpretation, collection run) may be retried; each attempt may spawn a **new** Celery task and thus a **new** task execution record. The tracker only records each run; it does not decide or implement retry.
- Status values (e.g. RETRY) in the record mean "Celery reports this state"; they are for observation and sync from the result backend, not for the tracker to trigger retries.

## What the abstraction provides (共性能力)

The module limits itself to **common capabilities** that all projects need:

1. **Task record**  
   One record per execution (keyed by task_id). Register at dispatch, optional sync from Celery.

2. **Real-time update**  
   Update status, result, error, traceback, metadata as the task runs or when it finishes (including from Celery).

3. **Exception handling (e.g. timeout)**  
   Support for recording and querying failure reasons (timeout, error, traceback). Timeout detection and handling (e.g. revoke, mark failed) are implemented in **business or worker code** (e.g. a periodic monitor task); the tracker only stores the outcome.

4. **Task lock**  
   Prevent duplicate execution (acquire/release/is_locked, `@prevent_duplicate_task`) so that the same logical task does not run concurrently when the business requires it.

No workflow engine, no built-in retry policy, no orchestration—only recording, real-time updates, and the above exception/lock capabilities.

---

## Schema: JSON fields vs table split

Detail data (task_args, task_kwargs, result, metadata) is stored in **JSON fields** in a single `TaskExecution` table. We do **not** split these into separate normalized tables.

**Why keep one table + JSON**

- **Usage**: Recording is side-channel; we **filter by scalar columns** (task_id, module, task_name, status, created_at, created_by) and **display** the payload. We do not query inside JSON for business logic (e.g. “find tasks where metadata contains X”).
- **Simplicity**: One table, no extra joins or FKs for details; easier migrations when different modules put different shapes in `metadata` / `result`.
- **Flexibility**: Each module can store arbitrary structures in `metadata` (e.g. `steps`, `logs`) without new columns or tables.

**When to consider splitting**

- **Query by content**: If you need to filter or report by fields *inside* result/metadata (e.g. “all tasks where result.status = 'partial'”), consider either JSONB indexes (PostgreSQL) or a normalized detail table.
- **Size**: If a single row’s result/metadata regularly grows very large (e.g. huge logs) and list APIs must avoid loading it, consider moving large blobs to a separate table and joining only in detail view. This is optional and only if profiling shows a real problem.

**Conclusion**: For “record once, update in real time, list/filter by scalar, show details as-is,” a single table with JSON fields is sufficient and preferred. No table split is required unless the above conditions appear later.
