# agentcore-task 设计结论摘要

本文档汇总当前形成的设计结论，便于评审与后续实现对齐。

---

## 一、定位与目标

- **定位**：统一的**任务执行旁路记录**与**任务锁**抽象，供 Newshub、Devify、easy-divine、devmind 等项目复用。
- **目标**：只提供各项目共用的能力，替代各项目内重复的 task lock 与 task 执行记录实现；不引入额外开源依赖。

---

## 二、设计原则

### 1. 旁路记录（side-channel recording）

- 任务执行记录是**旁路**：只记录「谁、何时、状态、结果、错误」，不驱动工作流、不拥有重试语义。
- 长时序任务需要的是**可查询、可持久化**的每次运行记录；记录与真实执行是**并行的**，业务逻辑与 Celery 仍是执行与调度的唯一真相源。

### 2. 业务层重试（retry is business concern）

- **重试属于业务层**，不属于 task tracker。
- 早期把「任务重试」作为 tracker 的一等概念（如 Newshub/Devify）是设计错误：把**记录**和**控制流**混在一起。
- 正确模型：**业务对象**（订单、解读、采集 run 等）可重试；每次重试可发起**新的** Celery 任务，从而产生**新的**一条执行记录。Tracker 只记录每一次运行，不决定、不实现重试。
- 记录中的 RETRY 等状态仅表示「Celery 报出的状态」，用于观测和与 result backend 同步，不用于由 tracker 触发重试。

### 3. 只提供共性能力

- 本模块**仅提供**所有项目都需要的共性能力，不做工作流引擎、不做内置重试策略、不做编排。

---

## 三、提供的共性能力（四条）

| 能力 | 说明 |
|------|------|
| **1. 任务记录** | 每次执行一条记录（以 task_id 为键）。派发时注册，可选从 Celery 同步。 |
| **2. 实时更新** | 运行中/结束时更新 status、result、error、traceback、metadata（含从 Celery 同步）。**支持运行中多次更新**：可在任务未完成时多次调用 `update_task_status(..., metadata={...})` 上报进度（如 progress_percent、progress_step），metadata 会合并更新，前端轮询任务详情即可看到最新进度，无需等任务全部执行完成。 |
| **3. 异常处理（如超时）** | 支持记录与查询失败原因（超时、错误、traceback）。超时的**发现与处理**（如 revoke、标失败）由业务或 worker 侧实现（如定时 monitor 任务），tracker 只存储结果。 |
| **4. 任务锁** | 防重复执行：acquire_task_lock / release_task_lock / is_task_locked / `@prevent_duplicate_task(lock_name, timeout, lock_param)`。 |

---

## 四、不做什么

- 不驱动工作流、不拥有重试策略、不做法人编排。
- 不提供「按前缀清理所有锁」；锁依赖 TTL 过期，清理可由项目在 worker 启动时自建。
- 不提供执行时长/按日统计（业务可用 TaskExecution 的 started_at/finished_at 自行聚合）。

---

## 五、与各项目的关系

- **需求一致**：Newshub、Devify、easy-divine 的底层需求一致——防重复执行（锁）+ 可查询的任务执行记录。easy-divine 的 task_manager 与 agentcore-task 已是同一套设计。
- **可替代**：三项目中的 task lock 与 task 执行记录均可由本模块替代；迁移时步骤/日志用 **metadata**（如 `metadata['steps']`、`metadata['logs']`）承载即可。

---

## 六、表结构与存储

- **单表 + JSON 字段**：详情（task_args、task_kwargs、result、metadata）存放在单表 `TaskExecution` 的 JSON 字段中，**不做表拆分**。
- **原因**：当前用法是「按标量字段筛选 + 展示 payload」，不对 JSON 内部做业务查询；单表简单、各模块可在 metadata 中自由扩展结构。
- **何时考虑拆分**：若未来需要按 result/metadata **内容**做筛选或索引，可考虑 PostgreSQL JSONB 索引或独立详情表；若单行体积过大且列表接口必须不加载大字段，再考虑大字段拆表。当前不做。

---

## 七、数据库推荐

- **推荐使用 PostgreSQL**。
- Django 的 JSONField 在 PostgreSQL / MySQL / SQLite 均可使用，但 **JSONB 及 JSONB 索引**（如 GIN）**仅 PostgreSQL 支持**。若后续需要对 metadata/result 内部做查询或索引，需使用 PostgreSQL。锁使用 Django cache 后端，与主库选型无关。

---

## 八、步骤/日志与进度约定

- 不提供独立的 steps 字段；步骤或日志统一放在 **metadata** 中（如 `metadata['steps']`、`metadata['logs']`）。
- 业务侧在运行中 append 后，通过 `update_task_status(..., metadata=...)` 写回即可；也可配合 TaskLogCollector 在任务结束时将日志写入 metadata。
- **执行进度**：进度也放在 **metadata** 中（如 `metadata['progress_percent']`、`metadata['progress_message']`、`metadata['progress_step']`）。任务运行过程中可**多次**调用 `update_task_status(task_id, status=..., metadata={"progress_percent": 50, ...})` 做实时进度上报；接口对 metadata 做合并（update），不整体覆盖，前端轮询任务详情即可拿到最新进度。  
  （说明：easy-divine 中当前进度是写在**业务模型** IChingInterpretation 的 interpretation 字段里，由记录详情 API 返回；若希望从「任务执行」维度查进度，可改为或同时写入 TaskExecution.metadata，本模块支持实时更新。）

---

## 相关文档

- 设计详述（英文）：[DESIGN.md](DESIGN.md)  
- 能力与替代结论：[CAPABILITY_CONFIRMATION.md](CAPABILITY_CONFIRMATION.md)  
- Newshub/Devify 对比分析：[NEWSHUB_DEVIFY_TASK_ANALYSIS.md](NEWSHUB_DEVIFY_TASK_ANALYSIS.md)  
- **任务状态命名**（与各项目对照及迁移映射）：[STATUS_VOCABULARY.md](STATUS_VOCABULARY.md)
