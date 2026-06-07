# Lens 模块 — CTO 完整设计文档（定稿 · 自包含）

> 仓库：**`/root/workspace/sourcelens/`** ｜ 栈：Django + DRF + Celery + Redis + PostgreSQL + Vue3 ｜ 日期：2026-06-01
> 状态：**board 已批准（2026-06-01）「设计没太大问题，可进入原型阶段」。** 含 board Q1–Q5 终裁 + LangChain/LangGraph 采用指示（§5.1）。本文为单篇自包含定稿，整合 rev4→rev6.1 全部内容，无需跳读历史版本。
> 维护说明：`lens` 是在 sourcelens 中**全新创建**的 Django app（sourcelens 不含旧 `ai_query`，天然 greenfield）。
> **rev3 errata（DEV-10，2026-06-01，CTO）**：非实质性补订，**不改 board 已批准的核心数据模型与架构**。① §8 SSE 加心跳/重连快照（M8，type 枚举 +`ping`/`sync`）+ §10 R4 配套；② §2/§9/§11「12 表」订正为「14 表」（L2）；③ §3.2 jira config 补 `credentials_ref`（L4）；④ H1 删除语义经确认**维持四处 `PROTECT` 不变**（无需改文）。完整裁定见 DEV-7 评论 `9a88d39c`。

---

## 0. 文本架构图

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          浏览器 / 前端 SPA（Vue3）                          │
│  Pages: Assistants / Chat(Session) / History / DataSources / Resources       │
│      ↓ axios (REST /api/lens/*)              ↓ EventSource (SSE)             │
└───────────────────────┬──────────────────────────────────┬──────────────────┘
                        │ REST(JSON)                       │ SSE(text/event-stream)
┌───────────────────────▼──────────────────────────────────▼──────────────────┐
│                        Django + DRF（lens app）                              │
│  views / serializers / permissions / urls                                    │
└──────┬───────────────────────┬───────────────────────────┬───────────────────┘
       │ ORM                   │ enqueue(Celery)            │ stream
       │                       ▼                            │
       │              ┌────────────────┐                    │
       │              │  Redis broker  │                    │
       │              └───┬────────────┘                    │
┌──────▼─────────┐    ┌───▼──────────────────────────────┐  │
│  PostgreSQL    │◀───│  Celery Worker (queue=lens)       │  │
│  (lens_* 表)   │ORM │  execute_answer_run               │  │
│ Assistant      │    │   └─ RunStep×4:                   │  │
│  AssistantSkill│    │      query_rewrite → retrieval    │──┼─┐
│  AssistantMCP  │    │      → answer → stream            │  │ │
│  AssistantData │    └───────────────────────────────────┘  │ │
│   Source(scope)│                                            │ │
│ DataSource(全局)│                   │ create/destroy        │ │
│ Session/Message│                   ▼                       │ │
│ Run/RunStep    │       ┌───────────────────────────────┐  │ │
│ Sandbox(1:1Run)│◀──────│   Docker Engine（宿主机）      │  │ │
│ Skill/MCPServer│snapshot│  临时 Sandbox 容器/每次 Run   │──┘ │
│ ScheduledTask  │       │  只读挂载 DataSource 本地缓存  │    │
│ GlobalSetting  │       │  安全加固 + 资源/网络限制      │    │
└──────┬─────────┘       └───────────────────────────────┘    │
       │ ScheduledTask 登记 / PeriodicTask 调度         ┌──────▼──────┐
       │                                                │ LLM Provider │
┌──────▼───────────────────────────┐                    │(agentcore_   │
│  Celery Beat (DatabaseScheduler)  │                    │ metering)    │
│  django-celery-beat.PeriodicTask  │                    └──────────────┘
│   ├─ source_sync(每 DataSource)   │ git pull / jira API / feishu API
│   ├─ sandbox_cleanup (全局)       │──────┐
│   └─ run_retention   (全局)       │      ▼
└───────────────────────────────────┘  ┌──────────────────────────────┐
                                        │ 宿主机本地缓存                │
                                        │ /var/lib/sourcelens/lens/cache│
                                        │  └─ <datasource_uuid>/        │
                                        └──────────────────────────────┘
local_dir 源：零拷贝，直接只读挂 config.path，不建缓存、不建 sync 任务
```

**三条路径**：①**同步**：Beat → `source_sync(datasource_id)` → 落完整数据到本地缓存。②**问答**：前端 `POST runs/` → 建 Run+Message → Celery 四阶段（RunStep）→ SSE 流式。③**持久化**：`Session ← Message ← Run ← RunStep` + 一等 `Sandbox(1:1 Run)`。

---

## 1. board 终裁（Q1–Q5，已全部落定）

| Q | 决策点 | board 裁定 | 落地 |
|---|---|---|---|
| Q1 | 迁移策略 | 重新初始化（greenfield） | sourcelens 内全新建 `lens` app + `0001_initial`，**不做数据迁移**（sourcelens 本就无 ai_query） |
| Q2 | `AuditEvent` | 本期暂不做 | 模型集**不含 AuditEvent**；安全事件靠 `RunStep.detail` + 脱敏日志兜底 |
| Q3 | 模型能力校验 | 按建议 | **Assistant 级一次性连通性校验**（保存时测三个 `*_model_ref`），不建 per-route 表 |
| Q4 | 访问控制 | 单独课题，本期不做 | **不建** visibility/权限集/staff；仅保留 `Session.user` 私有归属 |
| Q5 | `http_direct`/multimodal | 可以（按建议） | 本期**只实现 `claude_code`/`codex` 沙箱路径**；其余建模留位、不写执行逻辑 |

---

## 2. 命名（采纳 board 数据模型）

App = `lens`（sourcelens/backend/lens/）。模型采用简洁名、无任何 `AiQuery` 前缀。物理表 `lens_<snake>`，URL `/api/lens/*`，env `LENS_*`，Celery queue `lens`，SSE event `lens_event`。最终实体集（14 表）：`Assistant` / `AssistantSkill` / `AssistantMCP` / `AssistantDataSource` / `DataSource` / `Session` / `Message` / `Run` / `RunStep` / `Sandbox` / `Skill` / `MCPServer` / `ScheduledTask` / `GlobalSetting`。
（本期无 `AuditEvent`〔Q2〕、无 `ProjectModelRoute`〔被三 `*_model_ref` 取代〕、无 visibility/权限表〔Q4〕。）

---

## 3. 数据模型 — 字段级 `0001_initial`（实现就绪）

> 约定：所有表含 `uuid=UUIDField(default=uuid4, unique=True, editable=False)` + `created_at(auto_now_add)`/`updated_at(auto_now)`（除标注外）。app_label=`lens`，db_table=`lens_<snake>`。JSON 异构字段一律 serializer 层校验。FK 引用 `agentcore_metering.LLMConfig` 用其 `uuid`。

### 3.1 应用层

**Assistant**（`lens_assistant`）
| 字段 | 类型 | 说明 |
|---|---|---|
| name | CharField(160) | 显示名 |
| slug | SlugField(180, unique) | 对外标识 |
| capability_type | CharField(choices=`query`) | 本期仅 query |
| engine_type | CharField(choices=`claude_code,codex,deepagent,http_direct`) | **本期只实现 claude_code/codex**；其余执行层 `raise NotImplementedError` |
| engine_config | JSONField(default=dict) | 引擎连接参数（CLI 路径/端点） |
| preprocess_model_ref | UUIDField(null=True) | → LLMConfig.uuid（query 改写 + answer 整理） |
| engine_model_ref | UUIDField(null=True) | → LLMConfig.uuid（喂给 CLI 引擎自身） |
| multimodal_model_ref | UUIDField(null=True) | → LLMConfig.uuid；本期建模留位不调用 |
| settings | JSONField(default=dict) | 沙箱资源/网络默认（覆盖 GlobalSetting） |
| status | CharField(choices=`active,disabled`, default=active) | |

> Q3 校验：保存时对非空 `preprocess/engine_model_ref` 做一次性连通性校验，结果写 `settings['_model_check']`（status/checked_at/error），失败告警不强制阻断。

**AssistantSkill**（`lens_assistant_skill`）：`assistant`(FK,CASCADE)、`skill`(FK,PROTECT)、`enabled`(bool,default=True)、`load_config`(JSON,default=dict)；`unique_together(assistant, skill)`。
**AssistantMCP**（`lens_assistant_mcp`）：`assistant`(FK,CASCADE)、`mcp`(FK,PROTECT)、`enabled`、`load_config`；`unique_together(assistant, mcp)`。
**AssistantDataSource**（`lens_assistant_datasource`）：`assistant`(FK,CASCADE)、`datasource`(FK,PROTECT)、`enabled`(bool,default=True)、`retrieval_scope`(JSON,null=True)；`unique_together(assistant, datasource)`；index(assistant)。`retrieval_scope`=`{include_paths[],exclude_paths[],include_extensions[],exclude_extensions[],max_file_size,max_depth}`，null=不限。

### 3.2 数据源层

**DataSource**（`lens_datasource`，**全局资源库**）
| 字段 | 类型 | 说明 |
|---|---|---|
| name | CharField(160) | |
| source_type | CharField(choices=`git,jira,feishu,local_dir`) | |
| config | JSONField(default=dict) | 异构：git`{repo_url,branch,credentials_ref}` / feishu`{app_token,doc_ids,credentials_ref}` / jira`{base_url,auth_scheme,query_rules,field_mapping,credentials_ref}` / local_dir`{path}` |
| sync_policy | JSONField(default=dict) | `{interval_seconds, depth, ...}`；local_dir 忽略 |
| local_cache_path | CharField(500) | 宿主机缓存目录；local_dir 直指 config.path |
| last_synced_at | DateTimeField(null=True) | |
| status | CharField(choices=`active,disabled,error`, default=active) | |

index(status)。凭证只存 `config.credentials_ref`，**禁明文**。**无 assistant FK、无 retrieval_scope**（上移关联表）。

### 3.3 运行时层

**Session**（`lens_session`）：`assistant`(FK,PROTECT)、`user`(FK,CASCADE)、`title`(CharField160,blank)、`status`(choices=`active,archived`,default=active)。
**Message**（`lens_message`，仅 created_at）：`session`(FK,CASCADE)、`role`(choices=`user,assistant,system`)、`content`(Text,blank)、`run`(FK→Run,null=True,SET_NULL)、`sequence`(PositiveInt)；`unique_together(session, sequence)`；index(session, sequence)。线性记忆，不引向量库。
**Run**（`lens_run`）：`session`(FK,CASCADE)、`status`(choices=`queued,running,streaming,done,failed,cancelled`,default=queued,db_index)、`input_message`(FK→Message,PROTECT,related_name=request_runs)、`output_message`(FK→Message,null=True,SET_NULL,related_name=response_runs)、`error`(Text,blank)、`started_at`/`finished_at`(null=True)、`idempotency_key`(CharField128,blank)；`unique_together(session, idempotency_key)`；index(session, status)。
**RunStep**（`lens_run_step`）：`run`(FK,CASCADE)、`step_type`(choices=`query_rewrite,retrieval,answer,stream`)、`detail`(JSON,default=dict)、`status`(choices=`running,done,failed`)、`sequence`(PositiveInt)；index(run, sequence)。

### 3.4 执行基础设施层

**Sandbox**（`lens_sandbox`，`destroyed_at` 替代 updated_at）：`run`(OneToOne,CASCADE)、`container_id`(CharField128,blank)、`status`(choices=`creating,ready,destroyed`,default=creating)、`mounted_sources`(JSON,default=list，记 `[{datasource_uuid,applied_scope}]`)、`loaded_skills`(JSON,default=list)、`loaded_mcps`(JSON,default=list)、`resource_limits`(JSON,default=dict)、`destroyed_at`(DateTimeField,null=True)。

### 3.5 资源库（全局）

**Skill**（`lens_skill`）：`name`、`slug`(unique)、`definition`(JSON/Text)、`enabled`(bool,default=True)。
**MCPServer**（`lens_mcp_server`）：`name`、`transport`(choices=`url,stdio`)、`endpoint`(CharField500,blank)、`config`(JSON,default=dict)、`enabled`(bool,default=True)。

### 3.6 调度与配置

**ScheduledTask**（`lens_scheduled_task`，仅 updated_at）：`name`(CharField200)、`task_type`(choices=`source_sync,sandbox_cleanup,run_retention`)、`periodic_task_ref`(IntegerField,null=True → `django_celery_beat.PeriodicTask.id`，**调度真相源；本表不存 crontab**)、`target_type`(CharField64,null=True)、`target_id`(UUIDField,null=True)、`last_run_at`(null=True)、`last_status`(choices=`success,failed,running`,null=True)、`last_error`(Text,blank)、`last_metrics`(JSON,default=dict)、`enabled`(bool,default=True)；index(task_type)、index(target_type, target_id)。
**GlobalSetting**（`lens_global_setting`，无 uuid，`key` 主键，仅 updated_at）：`key`(CharField190,pk)、`value`(JSON)、`description`(CharField255,blank)。典型：`sandbox.defaults.timeout`、`sandbox.defaults.resource_limits`、`retention.run_days`。

### 3.7 ER 关系

```
Assistant ──< AssistantSkill        >── Skill        (全局)
          ├─< AssistantMCP          >── MCPServer    (全局)
          ├─< AssistantDataSource   >── DataSource   (全局)
          └─< Session ──< Run ──< RunStep
                  │         └──1:1── Sandbox
                  └──< Message (input/output ← Run)
ScheduledTask ┄(periodic_task_ref)┄> django_celery_beat.PeriodicTask
GlobalSetting (无外键)
```

---

## 4. 问答持久化链路（端到端时序）

```
T0  用户提问
T1  POST /api/lens/sessions/{uuid}/runs/   (atomic + SELECT FOR UPDATE 锁 Session)
     ├─ INSERT Message(role=user, sequence=N)
     ├─ INSERT Message(role=assistant, content="", sequence=N+1)  ← Run.output_message
     └─ INSERT Run(status=queued, input_message, output_message, idempotency_key)
T2  Celery worker pick → Run.status=running
     ├─ RunStep(query_rewrite): running→done(detail=改写结果)
     ├─ Sandbox(run): creating→ready(container_id, loaded_skills/mcps 快照, mounted_sources)
     ├─ RunStep(retrieval): running→done(detail=命中/工具调用)
     ├─ Sandbox: destroyed (try/finally) + destroyed_at
     ├─ RunStep(answer): running→done(detail=tokens)
     └─ RunStep(stream): running  ← SSE 推送阶段
T3  流式写 Message(assistant).content（≤200ms 或 100 token 节流，防热点行）
T4  Run.status=done, finished_at；RunStep(stream).done；Session.updated_at
T_err 任一 RunStep 失败 → 该 RunStep.failed；Run.failed + Run.error；
      Message(assistant) 保留已生成部分；Sandbox 强制 destroyed
```
幂等：`(session, idempotency_key)` 唯一去重（30s 内重复点击不新建 Run）。一致性：`transaction.atomic()` + Session 行锁防并发双活跃 Run。记忆：按 `session+sequence` 线性取历史拼进 LLM messages。

---

## 5. execution.py（四阶段 → RunStep + engine_type 分派）

```python
def execute_answer_run(run: Run) -> None:
    assistant = run.session.assistant
    with run_step(run, 'query_rewrite') as step:                       # 阶段一
        rewritten = LLMTracker(assistant.preprocess_model_ref).complete(run.input_message.content)
        step.detail = {'rewritten': rewritten}
    if assistant.engine_type == Assistant.Engine.HTTP_DIRECT:          # 阶段二（按引擎分派）
        raise NotImplementedError('LENS_ENGINE_NOT_IMPLEMENTED')       # 本期不实现（Q5）
    else:
        with run_step(run, 'retrieval') as step, sandbox_context(run) as sb:
            result = execute_agent_in_sandbox(sb, rewritten, assistant)
            evidence = parse_agent_output(result.stdout)
            step.detail = {'hits': evidence, 'exit_code': result.exit_code}
    with run_step(run, 'answer') as step:                              # 阶段三
        answer = LLMTracker(assistant.preprocess_model_ref).complete(build_answer_prompt(rewritten, evidence))
    with run_step(run, 'stream'):                                      # 阶段四
        stream_to_client(run, answer)   # emit lens_event；节流写 Message.content
```
- `run_step()`/`sandbox_context()` 为新 context manager，管 RunStep/Sandbox 状态机与 try/finally。
- 三模型角色：`preprocess_model_ref`=系统侧前后处理；`engine_model_ref`=喂给沙箱内 CLI；`multimodal_model_ref`=留位。
- 错误码：`LENS_SANDBOX_BUSY/TIMEOUT/EXEC_FAILED/NETWORK_DENIED`、`LENS_SOURCE_NOT_READY`、`LENS_ENGINE_NOT_IMPLEMENTED`。
- 旧 ai_query 的 SSE/LLMTracker/path-safety 等逻辑在 sourcelens 无物理文件，需在 lens 内**重新实现**（非 import）。

---

## 5.1 LangChain / LangGraph 采用策略（board 2026-06-01 指示）

board 指示：实现时尽量用 LangChain/LangGraph 等成熟框架，降低重复造轮子。CTO 评估后的**精准采用边界**（用对地方，不滥用）：

**用 LangGraph —— 编排四阶段（强匹配）**
- 把 `execute_answer_run` 四阶段建成一个 `StateGraph`：节点=query_rewrite/retrieval/answer/stream，状态=`{question, rewritten, evidence, answer, run_id}`。
- 条件边承载 `engine_type` 分派（claude_code/codex→沙箱节点；http_direct/deepagent→留位节点 `raise NotImplementedError`）。
- 每个图节点完成写一行 `RunStep`（节点↔RunStep 一一对应），天然支持可观测/重放；LangGraph checkpointer 可选用于断点续跑。
- 替代手写顺序编排，但 `execution.py` 对外签名 `execute_answer_run(run)` 不变。

**用 langchain-core —— LLM 周边原语（选择性）**
- `ChatPromptTemplate`：query_rewrite / answer 合成的 prompt 模板。
- 消息类型（Human/AI/SystemMessage）：把 `Message`（按 session+sequence 的简单记忆）转成 LLM messages。
- 输出解析器：结构化解析沙箱 Agent 输出 / evidence。

**关键约束：LLM 调用必须仍走 agentcore_metering 计量（不可被 LangChain 绕过）**
- 项目硬约束：所有 LLM 调用经 `agentcore_metering.LLMTracker` 计量。
- 故**不直接用** LangChain 厂商 LLM/ChatModel 类（会绕过计量）。
- 方案：实现薄适配器 `LensMeteredChatModel(BaseChatModel)`，内部委托 `LLMTracker`（按 `*_model_ref` 解析配置），对 LangGraph/LangChain 暴露标准 Runnable 接口；三类 `*_model_ref` 各构造一个适配器实例。
- 即：**编排/原语用 LangChain 生态，计量与配置仍归 agentcore_metering**，两者经适配器桥接。

**不使用的地方（避免过度采用）**
- 不替代 Django/DRF（API）、Celery（任务队列）、Docker 沙箱（沙箱内 claude_code/codex CLI 本身即 agent，不在其内跑 LangChain）。
- 不引入 LangChain AgentExecutor 包裹沙箱路径（CLI 即 agent）。
- LangGraph 只编排 **Celery worker 层外层流程**，沙箱是其中一个节点。

**依赖与版本**
- 新增 `langgraph` + `langchain-core`（不引入大而全的 `langchain` 元包）；pyproject 固定版本。
- 说明：board 明确指示新增的成熟框架，**取代** rev4 时代「不新增技术栈」约束在编排层的限制；计量/任务/Web/前端栈不变。

---

## 6. services/sandbox.py（Sandbox 一等模型 + 安全加固）

```python
def create_sandbox_container(assistant, run) -> Sandbox:
    """启动容器并 INSERT Sandbox 行。
    - 安全加固（默认开启）：security_opt=['no-new-privileges'], cap_drop=['ALL'],
      pids_limit=50, user='nobody', read_only=True, tmpfs={'/tmp':'size=64m'}
    - 资源/网络：assistant.settings ∪ GlobalSetting('sandbox.defaults.*')；默认 network=none
    - 只读挂载：遍历该 Assistant 的 AssistantDataSource(enabled=True)，按各自 retrieval_scope
      挂对应全局 DataSource 的 local_cache_path 子树（local_dir 直挂 config.path）。
      ★ scope 过滤在【挂载阶段】执行（源全局共享，同步阶段不能按单 Assistant 过滤）。
    - 快照：loaded_skills/loaded_mcps 从关联表(enabled=True)固化；mounted_sources 记 (ds_uuid, applied_scope)
    - labels: {lens.run_id, lens.managed=1}
    """
def execute_agent_in_sandbox(sandbox, question, assistant) -> SandboxResult: ...
def cleanup_container(container_id) -> None: ...           # 幂等强删
@contextmanager
def sandbox_context(run): ...                              # try/finally 守卫 + Sandbox 状态机
def acquire_container_slot(assistant, *, block, timeout_s) -> bool: ...   # Redis 槽位
def release_container_slot(assistant) -> None: ...
def reap_orphan_containers() -> int: ...                   # 扫 labels 对照 Run.status 强删（sandbox_cleanup 调度）
```
并发槽位：Redis 键 `lens:sandbox:slots:{assistant_uuid}`，Lua 脚本保证 INCR/DECR 不溢出；`reap_orphan_containers` 兜底漏 release。

---

## 7. 数据源同步 + 调度

```python
@shared_task(name='lens.source_sync', queue='lens', autoretry_for=(SyncTransient,), retry_backoff=True)
def source_sync_task(datasource_id):
    ds = DataSource.objects.get(uuid=datasource_id)        # 全局源，按 DataSource 触发
    st = ScheduledTask.objects.get(task_type='source_sync', target_type='datasource', target_id=ds.uuid)
    with datasource_lock(ds.uuid, ttl_s=600):
        st.last_status='running'; st.save()
        try:
            n = _sync_by_type(ds)        # git pull/jira/feishu；落【完整数据】到 local_cache_path（不按 scope 过滤）
            ds.last_synced_at=now(); ds.status='active'; st.last_status='success'; st.last_metrics={'synced':n}
        except Exception as e:
            ds.status='error'; st.last_status='failed'; st.last_error=_mask(e); raise
        finally:
            ds.save(); st.last_run_at=now(); st.save()
```
- 调度复用 `core.periodic_registry.TASK_REGISTRY` → 写入 `django_celery_beat.PeriodicTask`（**调度唯一真相源，不双写**）。
- 全局任务（`sandbox_cleanup`/`run_retention`）：`register_periodic_tasks()` 注册 + 一行 `ScheduledTask(target_type=null)`。
- per-DataSource `source_sync`：新建 git/jira/feishu 源时建 PeriodicTask + `ScheduledTask(target_type=datasource)`；**每源一条，与 Assistant 数量无关**。
- `local_dir`：不建 sync 任务；`local_cache_path` 直指 `config.path`，挂载阶段按 scope 过滤 + 校验可读性。

---

## 8. 前端技术方案与 API 契约

技术栈：**Vue 3.4 + Pinia 2 + Vue Router 4 + Tailwind 3 + Vite 5**（sourcelens/frontend 现有栈）；`marked`+`dompurify`+`highlight.js` 渲染。新增 `store/lens.js`、`api/lens.js`；复用现有 axios 单例。前端原型由 PM 完成，CTO 只定范围与契约。

| 路由 | 组件 | 说明 |
|---|---|---|
| `/lens/assistants` | `Assistants.vue` | Assistant 列表 |
| `/lens/assistants/:slug/chat` | `Chat.vue` | 问答（SSE 流式 + RunStep 阶段进度条） |
| `/lens/assistants/:slug/history` | `History.vue` | 本人 Session/Message 历史 |
| `/lens/admin/assistants` | `Admin/Assistants.vue` | Assistant CRUD + engine/三模型引用 + 绑定 Skill/MCP/DataSource（配 retrieval_scope） |
| `/lens/admin/datasources` | `Admin/DataSources.vue` | 全局 DataSource CRUD + 同步状态 |
| `/lens/admin/resources` | `Admin/Resources.vue` | Skill/MCPServer/DataSource 全局资源库 |

**REST**（`/api/lens/*`）：`assistants/`、`assistants/{uuid}/datasources/`（绑定+配 scope）、`sessions/`、`sessions/{uuid}/messages/`、`sessions/{uuid}/runs/`、`runs/{uuid}/`（含 RunStep 时间线）、`runs/{uuid}/cancel/`、`admin/datasources/`(+`/{uuid}/sync/`)、`admin/skills/`、`admin/mcp-servers/`。

**SSE**（`GET /api/lens/runs/{uuid}/stream/`，事件名 `lens_event`）：
```json
{"type":"step|token|evidence|done|error|ping|sync","step":"query_rewrite|retrieval|answer|stream",
 "content":"...","evidence":[...],"error":{"code":"...","message":"..."},"ts":"ISO-8601"}
```
前端按 `step` 渲染四阶段进度条；`done` 主动 close；`error` 标记失败。

**SSE 韧性（M8 定调，MVP，T4 实现前定稿）：**
- **应用层心跳（✅ MVP 采纳）**：流式期间每 **15s** 发一帧 keepalive，优先用 SSE 注释帧 `: ping <ts>\n\n`（EventSource 自动忽略、但重置代理/LB 空闲计时器，前端零改动），`retrieval` 阶段（最长静默窗口）必须发；可选具名 `{"type":"ping"}` 供 UI 显示「仍在处理」。
- **断线重连续传（✅ MVP 采纳「持久化快照」，不做 `Last-Event-ID` 重放）**：复用 §4 已落库的 `Run`/`RunStep`/`Message.content`。每次 (重)打开 stream，服务端**先发 `{"type":"sync","status":...,"steps":[...],"content":"<已累积助手内容>"}` 快照**，再续发实时 token；浏览器 EventSource 自动重连负责传输层，前端以 `sync` 对账避免重复渲染。Run 已 `done/failed/cancelled` 时发 `sync`(全量)+`done|error` 后 close。兜底：随时可 `GET runs/{uuid}/` 重建进度。
- **`Last-Event-ID` 逐 token 精确重放（⏸ 延期 post-MVP）**：需服务端逐帧 `id:` + per-run 事件缓冲/重放游标；MVP 由上面的 `sync` 快照覆盖，非必需。

---

## 9. Migration（greenfield，sourcelens）

1. 在 `sourcelens/backend/` 新建 `lens/` app（`apps.py` name=`lens`）——全新创建，无前身。
2. `lens/migrations/0001_initial.py`：按 §3 生成全部 14 表，一次成型。
3. `INSTALLED_APPS` 加 `'lens'`（sourcelens 无 ai_query，无需移除/搬运旧 app；content_type/permission 零负担）。
4. `register_periodic_tasks()`：注册全局 `sandbox_cleanup`/`run_retention` PeriodicTask + 对应 `ScheduledTask(target_type=null)`；保留天数读 `GlobalSetting('retention.run_days')`。
5. 前端 `sourcelens/frontend/` 新增 `/lens/*` 路由与页面。
6. DB：生产 `DB_ENGINE=postgresql`（验收无 SQLite）。

---

## 10. 风险

| # | 风险 | 处置 |
|---|---|---|
| R1 | 沙箱共享内核，内核漏洞逃逸残留风险 | 文档显式声明；多层加固；后续评估 gVisor |
| R2 | Redis 槽位 INCR/DECR 在 worker 异常时可能漏 DECR | Lua 脚本 + `reap_orphan_containers` 兜底巡检 |
| R3 | Git/凭证误写日志泄漏 | `config.credentials_ref` 间接存储 + 日志 mask + review/CI grep 钩子 |
| R4 | SSE 经 Nginx 需禁 buffering / 长静默期被代理切断 | `proxy_buffering off` + **`proxy_read_timeout` ≥ 心跳间隔×3（≥45s）** + 应用层 15s 心跳（§8 M8）；后端 `StreamingHttpResponse` 每帧 flush |
| R5 | 全局源缓存存完整数据，磁盘占用比同步时过滤略大 | 接受（换复用正确性）；必要时加 source 级总量上限 |
| R6 | `http_direct`/`deepagent`/multimodal 本期未实现 | 执行层 `raise NotImplementedError`；建模留位 |
| R7 | LangChain 生态迭代快、易 churn | 把 LangChain 表面积限制在 execution.py 编排 + prompt 原语，藏在现有 service 接口之后；只用 `langgraph`+`langchain-core` 并固定版本，便于将来替换 |

---

## 11. 实现路线（T1–T7，供 CEO 派发）

| # | 子任务 | 负责 | 依赖 |
|---|---|---|---|
| T1 | `lens` app 脚手架 + `0001_initial`（§3 全 14 表）+ admin | Developer | — |
| T2 | DRF：serializers/views/urls/permissions（§8 REST + SSE） | Developer | T1 |
| T3 | `services/sandbox.py`（Sandbox 持久化 + 加固 + 槽位 + 孤儿回收） | Developer | T1 |
| T4 | `services/execution.py` 四阶段 → **LangGraph StateGraph**（节点↔RunStep）；engine 分派；`LensMeteredChatModel` 适配器桥接 LLMTracker（§5.1） | Developer | T1,T3 |
| T5 | `source_sync` + ScheduledTask/PeriodicTask 注册 + local_dir 归一 | Developer | T1 |
| T6 | 前端 `pages/Lens/*`（PM 出原型后实现） | PM→Developer | T2 |
| T7 | QA：`manage.py lens_*` 测试 CLI + E2E | QA | T2,T4 |
| 可选 | Challenge Agent 对本设计独立挑战（加固/SSE 一致性/凭证） | Challenge | 本文 |

---

## 12. 验收对照（DEV-7）

- ✅ 无 FastAPI/APScheduler/SQLite（生产 postgresql）
- ✅ App 统一 `lens`，无 `ai_query` 残留（sourcelens greenfield）
- ✅ 模型名无 `AiQuery` 前缀（Assistant/DataSource/Session/Message/Run/...）
- ✅ 文本架构图在文档开头（§0）
- ✅ 前端技术方案 + API 契约清晰（§8）
- ✅ 问答持久化链路完整（§4，Session/Message/Run/RunStep/Sandbox）
- ✅ 代码引用匹配 `/root/workspace/sourcelens/backend/lens/...`
- ✅ board Q1–Q5 全部落定，设计冻结，可进入实现
