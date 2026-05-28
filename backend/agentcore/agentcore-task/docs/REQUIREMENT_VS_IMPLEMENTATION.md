# agentcore-task 需求与实现对照审查

本文档对照设计结论（DESIGN_SUMMARY.md）与当前实现，确认 agentcore_task 能否满足 devmind、Newshub、Devify、easy-divine 等项目的共性需求。

---

## 一、设计要求的四条共性能力

| 能力 | 设计要求 | 当前实现 | 状态 |
|------|----------|----------|------|
| **1. 任务记录** | 每次执行一条记录（task_id 为键）；派发时注册；可选从 Celery 同步 | `register_task_execution()` / `TaskTracker.register_task()`；`TaskExecution` 以 task_id 唯一；`TaskTracker.sync_task_from_celery()` | ✅ 满足 |
| **2. 实时更新** | 运行中/结束时更新 status、result、error、traceback、metadata；支持运行中多次更新 metadata（如进度） | `TaskTracker.update_task_status(task_id, status=..., result=..., error=..., traceback=..., metadata=...)`；metadata 合并更新 | ✅ 满足 |
| **3. 异常处理（如超时）** | 记录失败原因；超时发现与处理由业务或 monitor 实现，tracker 只存储 | 存储：update_task_status(FAILURE, error=..., traceback=...)；**内置**定时任务 `mark_timed_out_task_executions` 将超时 STARTED 置为 FAILURE（可配置间隔与超时时间） | ✅ 满足（并超出：提供内置超时检测） |
| **4. 任务锁** | 防重复执行：acquire/release/is_locked、@prevent_duplicate_task | `acquire_task_lock` / `release_task_lock` / `is_task_locked` / `@prevent_duplicate_task(lock_name, lock_param, timeout)`（services.task_lock） | ✅ 满足 |

---

## 二、当前实现提供的额外能力

以下为设计之外的增强，用于支撑多项目运维与配置一致性：

| 能力 | 说明 |
|------|------|
| **清理历史记录** | `cleanup_old_executions()`；Celery 定时任务 `cleanup_old_task_executions`（crontab 可配置，默认每天 2:00）；支持仅清理已完成、分批删除 |
| **超时自动置失败** | `mark_timed_out_executions()`；Celery 定时任务 `mark_timed_out_task_executions`（crontab 默认每 30 分钟；超时时间默认 10 分钟，可配置） |
| **全局/用户配置** | `TaskConfig` 模型（scope=global/user）；当前使用：`retention_days`、`timeout_minutes`，可从 Admin 配置，优先于 settings |
| **Beat 自动注册** | AppConfig.ready() 中在启用时自动将清理、超时两任务合并进 `CELERY_BEAT_SCHEDULE` |
| **任务级重试配置** | `get_task_retry_kwargs()`；Celery 任务可统一使用自动重试（max_retries、backoff 可配置） |
| **REST API** | 列表/详情/按 task_id/status/stats/sync；过滤：module、task_name、status、created_by、日期范围 |
| **自记录** | 清理、超时两个定时任务自身也会写入 TaskExecution（module=agentcore_task），便于审计 |

---

## 三、与各项目需求对应关系

- **devmind（主项目）**  
  - 已接入：cloud_billing 等使用 `agentcore_task.adapters.django` 的 register、update_task_status、lock、prevent_duplicate_task。  
  - 需求：任务记录、防重、进度/结果查询、清理与超时。  
  - **结论**：当前实现可满足，且已在使用。

- **easy-divine**  
  - 设计结论中与 agentcore-task 一致；迁移时用 metadata 承载步骤/进度即可。  
  - **结论**：可完全由本模块替代原有 task 记录与锁。

- **Newshub / Devify**  
  - 底层需求一致：防重复执行 + 可查询的任务执行记录。  
  - 状态命名与 Celery/easy-divine 统一；Newshub/Devify 若沿用旧状态名，迁移时需做一次映射（参见 STATUS_VOCABULARY.md）。  
  - **结论**：可替代；重试语义放在业务层（业务对象重试并发起新 Celery 任务），本模块只记录每次运行。

---

## 四、可能缺口与建议

| 项目 | 可能需求 | 当前支持 | 建议 |
|------|----------|----------|------|
| 所有 | 按「业务对象」维度查多次运行（如同一订单的多次重试） | 无业务对象 ID 字段 | 业务侧在 `metadata` 中存业务 ID（如 order_id、interpretation_id），列表/筛选通过 API 或自定义 view 按 metadata 过滤（或 PG JSONB 索引） |
| 所有 | 进度展示 | metadata 推荐字段：progress_percent、progress_message、progress_step；实时 update_task_status(..., metadata={...}) | 已支持；前端轮询任务详情即可 |
| Newshub/Devify | 与旧状态枚举兼容 | 状态与 Celery 一致，与两项目旧表可能不同 | 迁移时做状态映射；新数据统一用本模块状态 |

---

## 五、结论

- **四条共性能力**（任务记录、实时更新、异常/超时记录、任务锁）均已实现，且与 DESIGN_SUMMARY 一致。  
- **清理、超时、TaskConfig、Beat 自动注册、重试配置、REST API、自记录** 等增强已就绪，可支撑多项目统一运维与配置。  
- **devmind、easy-divine、Newshub、Devify** 的共性需求均可由当前 agentcore_task 满足；迁移时仅需：接入本模块、状态映射（如有）、业务重试改为「新 Celery 任务 + 新记录」、可选在 metadata 中挂业务 ID 便于按业务对象查多轮执行。
