# Agentcore Metering

[English](README.md)

面向 Django 项目的 AI 调用与统计统一模块。

- 使用 **LiteLLM** 进行补全与成本统计。
- 成本以金额 + 币种存储（如 `cost`、`cost_currency`）。
- 默认成本币种为 USD（由 LiteLLM 侧给出）。

---

## 安装

- **未上架 PyPI**，仅支持从 GitHub 安装。

**从 GitHub 安装**（克隆后可编辑）：
```bash
pip install -e git+https://github.com/cloud2ai/agentcore-metering.git
```
若主项目以 submodule 方式引用，在仓库根目录执行：
```bash
pip install -e path/to/agentcore-metering
```
- 主项目 Dockerfile 需遍历 `agentcore/` 下各子模块并执行 `pip install -e`。
- 详细说明见主项目 README。

---

## 测试

安装开发依赖后，在包根目录执行 pytest：

```bash
pip install -e ".[dev]"
pytest tests -v
```

- 单元测试覆盖：
  - `usage_stats`（解析、汇总、按模型、时间序列）
  - `usage`（分页列表与查询解析）
- API 测试覆盖：
  - `GET .../token-stats/`
  - `GET .../llm-usage/`
  - `llm-config` 相关接口（鉴权与响应结构）

---

## 后端使用

1. **注册**
   - 在 `INSTALLED_APPS` 中加入 `'agentcore_metering.adapters.django'`
   - 在根 URLconf 中加入 `path('api/v1/admin/', include('agentcore_metering.adapters.django.urls'))`
2. **调用 LLM 并落库用量**：
   ```python
   from agentcore_metering.adapters.django import LLMTracker
   content, usage = LLMTracker.call_and_track(
       messages=[{"role": "user", "content": "..."}],
       node_name="my_node",
       state=request_state,
   )
   ```
   - `state` 为可选（任务/用户上下文）。
   - 若 `state` 中包含 `user_id`，且该用户配置了单独 LLM 配置，则按用户配置调用。可传 `model_uuid` 指定使用某条配置；不传则使用最早启用的模型。
   - `json_mode=True` 且非流式时，默认启用 JSON 修复+校验并重试（`json_attempts=3`，可配置）。
   - `stream=True` 时不做 JSON repair（流式输出行为不变）。
3. **配置**
   - 所有配置可通过管理 API 管理（全局默认 + 可选按用户覆盖）。
   - 未指定 model_uuid 时，解析取最早创建的启用配置（按 created_at，全局可设 is_default）：用户作用域 -> 全局作用域；无 DB 配置时报错，不做 settings 回退。
   - LLM 调用经 **LiteLLM**。
   - 费用（USD）按 LiteLLM 参考价估算并写入单次调用与统计。

### 支持的提供商

- 各提供商默认使用最小/最便宜模型，降低误配成本。
- 可在 `config` 中覆盖 `model`，并按需覆盖 `api_base`、`deployment`。
- **所有提供商均支持 `api_base`（URL）**：
  - 未设置时使用官方端点
  - 需要时可设为代理/转发 URL

| 提供商        | 默认模型 / 说明 |
|-----------------|------------------|
| `openai`        | gpt-4o-mini（官方默认 URL） |
| `azure_openai`  | gpt-4o-mini（需提供 `api_base` 与 `deployment`） |
| `gemini`        | gemini-2.0-flash |
| `anthropic`     | claude-3-5-haiku |
| `mistral`       | mistral-tiny |
| `dashscope`     | qwen-turbo（阿里通义） |
| `deepseek`      | deepseek-chat |
| `xai`           | grok-3-mini-beta（Grok） |
| `meta_llama`    | Llama-3.3-8B-Instruct |
| `amazon_nova`   | nova-micro-v1 |
| `nvidia_nim`    | meta/llama3-8b（NVIDIA NIM / Nemotron） |
| `minimax`       | MiniMax-M2.1 |
| `moonshot`      | moonshot-v1-8k（Kimi） |
| `zai`           | glm-4.5-flash（智谱 GLM） |
| `volcengine`    | doubao-pro-32k（字节豆包） |
| `openrouter`    | google/gemma-2-9b-it:free |

- 配置仅来自 DB（管理 API），不做 Django settings 回退；需至少有一条启用的全局或用户配置方可调用。

---

## API 参考

- 挂载在管理前缀下（如 `api/v1/admin/`）。
- **鉴权**：`IsAdminUser`（staff 或 superuser），否则 403。
- 若主项目启用 drf-spectacular，可在 Swagger UI（如 `/swagger`）查看，标签为 **llm-metering**。

### LLM 配置（全局与按用户）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `.../llm-config/` | 获取全局 LLM 配置列表（按 created_at、id 排序） |
| POST | `.../llm-config/` | 新增一条全局配置。Body：`provider`、`config`（及可选 `is_active`） |
| GET | `.../llm-config/<pk>/` | 获取指定 id 的配置 |
| PUT | `.../llm-config/<pk>/` | 更新指定 id 的配置 |
| DELETE | `.../llm-config/<pk>/` | 删除指定 id 的配置 |
| GET | `.../llm-config/providers/` | 各提供商参数 schema（必填/可选键、默认 model 与 api_base），用于构建表单 |
| GET | `.../llm-config/models/` | 提供商与模型列表（含能力标签，如 text-to-text/vision/code/reasoning） |
| POST | `.../llm-config/test/` | 校验凭证且不保存。Body：`provider`、`config`。返回 `{ "ok": true }` 或 `{ "ok": false, "detail": "..." }` |
| POST | `.../llm-config/test-call/` | 执行一次测试调用并落库。Body：`config_uuid`（或兼容 `config_id`）、`prompt`，可选 `max_tokens`、可选 `stream`（见下） |
| GET | `.../llm-config/users/` | 按用户配置列表（可选 `?user_id=` 筛选） |
| GET | `.../llm-config/users/<user_id>/` | 获取指定用户的配置（未设置则 404） |
| PUT | `.../llm-config/users/<user_id>/` | 创建或更新该用户的配置 |
| DELETE | `.../llm-config/users/<user_id>/` | 删除该用户配置（回退到全局默认） |

- **POST/PUT body**
  - `provider`（默认 `openai`）
  - `config`（单层 JSON，如 `api_key`、`model`、`api_base`、`deployment`、`max_tokens`、`temperature`、`top_p`）
  - 创建/列表管理场景可额外传 `scope`、`user_id`、`is_active`、可选 `model_type`
  - 必填/可选键因提供商而异（如 Azure 需 `api_base`、`deployment`）
  - 可通过 `GET .../llm-config/providers/` 获取 schema
  - GET 返回中 `config.api_key`、`config.key` 会脱敏（如 `sk-**xxxx`）；`is_default` 表示该条是否为当前默认配置（未传 model_uuid 时使用的「最早启用的全局配置」），前端可用于高亮展示默认模型。

- **GET `.../llm-config/providers/`**
  - 返回格式：`{ "providers": { "<provider>": { "required": [...], "optional": [...], "editable_params": [...], "default_model": "...", "default_api_base": "..." } } }`
  - 用于渲染按提供商区分的表单与占位符

- **POST `.../llm-config/test/`**
  - body：`provider`、`config`（与 PUT 同）
  - 执行一次最小补全，验证 key 与端点
  - 成功：`200` + `{ "ok": true }`
  - 校验/调用失败：`200` + `{ "ok": false, "detail": "错误信息" }`
  - 请求体不合法：`400`

- **POST `.../llm-config/test-call/`**
  - body：`config_uuid`（推荐）或兼容 `config_id`、`prompt`（必填）、可选 `max_tokens`（默认 512，最大 4096）、可选 `stream`（默认 false）
  - `stream` 为 false（默认）时：JSON 响应。成功：`{ "ok": true, "content": "...", "usage": { ... } }`；失败：`{ "ok": false, "detail": "..." }`
  - `stream` 为 true 时：响应为 SSE（`Content-Type: text/event-stream`）。事件：每段内容 `data: {"type":"chunk","content":"<片段>"}`；结束事件 `data: {"type":"done","ok":true,"usage":{...}}` 或 `data: {"type":"done","ok":false,"detail":"..."}`
  - 调用会落到 usage 记录；流式调用以 `is_streaming=true` 记录，并可记录 TTFT（`first_chunk_at`）

- **模型能力标签与推理**
  - `GET .../llm-config/models/` 返回各提供商模型列表与能力标签（如 `text-to-text`、`vision`、`code`、`reasoning`）
  - `reasoning` 表示模型支持扩展推理/思维链（如 o1、o1-mini、deepseek-reasoner）
  - 推理强度/档位由厂商 API 参数控制（如 OpenAI `reasoning.effort`: `low/medium/high`）
  - 本模块只透传 config 参数，不单独维护推理档位
  - 前端可对带 `reasoning` 标签模型展示“支持推理”，具体档位按厂商文档传入

---

### GET `.../token-stats/`

- 返回汇总与可选时间序列。
- Query 参数均可选：

| 参数          | 类型   | 说明 |
|---------------|--------|------|
| start_date    | string | 开始时间，ISO 或仅日期（如 2025-01-01） |
| end_date      | string | 结束时间；仅日期时表示该日 23:59:59 |
| user_id       | int    | 按用户 id 筛选 |
| granularity   | string | 时间桶：`day`（按小时）、`month`（按天）、`year`（按月）；不传则不返回 series |
| use_series    | string | `1` / `true` / `yes`：与 granularity、日期范围一起传时，额外返回预聚合表 LLMUsageSeries 的 `series_by_model`，用于「按模型」趋势图 |

**200**（JSON）：

```json
{
  "summary": { ... },
  "by_model": [ ... ],
  "series": null,
  "series_by_model": null
}
```

- 仅当传入 `granularity` 时 `series` 非空：`{ "granularity": "day", "items": [ { "bucket": "...", "total_tokens": 0, ... } ] }`
- 仅当传入 `use_series=1`（或 `true`/`yes`）且同时有 `granularity` 与 `start_date`/`end_date` 时 `series_by_model` 非空。其为预聚合表的一条条 `{ "bucket", "model", "call_count", "success_count", "avg_e2e_latency_sec", "avg_ttft_sec", "avg_output_tps", "total_*_tokens", "total_cost", "cost_currency" }`，为全局数据（不按 user_id 过滤），用于「Token 趋势（按模型）」与「费用趋势（按模型）」等图表。
- `granularity` 非法时返回 `400` + `{ "detail": "..." }`

---

### GET / PATCH `.../metering-config/`

- **GET**：返回当前生效的计量配置（保留天数、清理与汇总的 cron）。
- **PATCH**：更新配置。Body 字段均可选：`retention_days`（1–3650）、`cleanup_enabled`、`cleanup_crontab`、`aggregation_crontab`（五段 cron 表达式）。

**GET 200**（JSON）：

```json
{
  "retention_days": 365,
  "cleanup_enabled": true,
  "cleanup_crontab": "0 2 * * *",
  "aggregation_crontab": "5 * * * *"
}
```

- 管理端「定时任务 / 数据设置」页通过该接口配置数据保留时长与清理/汇总执行时间。

---

### GET `.../llm-usage/`

- 返回分页用量列表。
- Query 参数如下：

| 参数       | 类型   | 说明 |
|------------|--------|------|
| page       | int    | 页码，默认 1 |
| page_size  | int    | 每页条数，默认 20，最大 100 |
| user_id    | int    | 按用户 id 筛选 |
| model      | string | 模型名（icontains） |
| success    | string | `true` / `false` 成功/失败 |
| start_date | string | 开始时间 |
| end_date   | string | 结束时间 |

**200**（JSON）：

```json
{
  "results": [
    {
      "id": "uuid",
      "user_id": "uuid-or-null",
      "username": "string-or-null",
      "model": "gpt-4",
      "prompt_tokens": 100,
      "completion_tokens": 50,
      "total_tokens": 150,
      "cost": 0.0012,
      "cost_currency": "USD",
      "success": true,
      "error": null,
      "created_at": "2025-01-01T12:00:00+00:00",
      "metadata": {}
    }
  ],
  "total": 100,
  "page": 1,
  "page_size": 20
}
```

---

- **使用建议**
  - 仪表盘与趋势图：`token-stats`
  - 可筛选、可分页调用明细：`llm-usage`

---

## 预聚合序列（LLMUsageSeries）

- **表**：`llm_usage_series` 按 **(granularity, bucket, model)** 预聚合。粒度：`hour`（对应「按天」视图）、`day`（对应「按月」）、`month`（对应「按年」）。
- **每行字段**：`bucket`、`model`、`call_count`、`success_count`、`avg_e2e_latency_sec`、`avg_ttft_sec`、`avg_output_tps`，以及各类 token 合计与 `total_cost`、`cost_currency`。
- **写入**：Celery 任务 `aggregate_llm_usage_series_task`（由 beat 触发时一次跑 hour + day + month）从 `llm_tracker_usage` 聚合写入 `llm_usage_series`，用于按模型趋势图的高效查询。
- **接口**：`GET .../token-stats/?use_series=1&granularity=...&start_date=...&end_date=...` 返回 `series_by_model`（上述行的列表）供前端绘图。

---

## 计量配置与定时任务

- **配置**：`MeteringConfig`（单行）存 `retention_days`（默认 365）、`cleanup_enabled`、`cleanup_crontab`、`aggregation_crontab`。接口见上文 `GET/PATCH .../metering-config/`。
- **Celery 任务**（需安装 Celery 与 `agentcore-task`，由 django-celery-beat 注册）：
  - **清理**：`cleanup_old_llm_usage_task` — 删除早于 `retention_days` 的 `llm_tracker_usage` 与 `llm_usage_series`。若 `cleanup_enabled` 为 false 则不执行。
  - **汇总**：`aggregate_llm_usage_series_task` — 一次执行 hour、day、month 三种粒度汇总，写入 `llm_usage_series`。
- **任务跟踪**：上述两个任务均通过 **agentcore-task** 的 `TaskTracker` 登记（模块名 `agentcore_metering`），执行记录会出现在统一任务列表与统计中（状态、result、error）。

---

## 数据与结构

- **表**：`llm_tracker_usage`（用量记录）、`llm_usage_series`（预聚合序列）、`agentcore_metering_llm_config`（LLM 配置）、`MeteringConfig`（保留天数与 cron 配置）。
- **包**：`agentcore_metering.adapters.django` 为完整 Django 应用（models、views、urls、admin、migrations）。业务逻辑在 `adapters/django/services/`（如 `runtime_config`、`config_source`、`usage`、`usage_stats`）；对外调用入口在 `adapters/django/trackers/`，LLM 为 `trackers/llm.py`。建议从 `agentcore_metering.adapters.django` 或 `agentcore_metering.adapters.django.trackers.llm` 导入 `LLMTracker`。后续若有其他 tracker 可在 `trackers/` 下新增模块（如 `other.py`）。
