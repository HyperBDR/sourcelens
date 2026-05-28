# Agentcore Metering

[中文](README.zh-CN.md)

Unified module for AI service invocation and statistics in Django projects.

- Uses **LiteLLM** for completion and cost metering.
- Stores cost as amount + currency (e.g. `cost`, `cost_currency`).
- Uses USD as default cost currency from LiteLLM.

---

## Install

- **Not on PyPI**, install only from GitHub.

**From GitHub** (editable after clone):
```bash
pip install -e git+https://github.com/cloud2ai/agentcore-metering.git
```
Or, when the host project uses it as a submodule, from repo root:
```bash
pip install -e path/to/agentcore-metering
```
- The host project Dockerfile should iterate over `agentcore/`
  submodules and run `pip install -e`.
- See the host project README for details.

---

## Testing

Install with dev extras, then run pytest from the package root:

```bash
pip install -e ".[dev]"
pytest tests -v
```

- Unit tests cover:
  - `llm_usage_stats` (parse, summary, by_model, series)
  - `llm_usage` (paginated list and query parsing)
- API tests cover:
  - `GET .../token-stats/`
  - `GET .../llm-usage/`
  - `llm-config` endpoints (auth and response shape)

---

## Backend: usage

1. **Register**
   - Add `'agentcore_metering.adapters.django'` to `INSTALLED_APPS`
   - Add `path('api/v1/admin/', include('agentcore_metering.adapters.django.urls'))` to root URLconf
2. **Call LLM and persist usage**:
   ```python
   from agentcore_metering.adapters.django import LLMTracker
   content, usage = LLMTracker.call_and_track(
       messages=[{"role": "user", "content": "..."}],
       node_name="my_node",
       state=request_state,
   )
   ```
   - `state` is optional (task/user context).
   - If `state` contains `user_id`, per-user LLM config (if set) is used. Pass `model_uuid` to use a specific config; otherwise the earliest enabled model is used.
   - For `json_mode=True` (non-stream), tracker does JSON repair + validation and retries by default (`json_attempts=3`; configurable).
   - For `stream=True`, JSON repair is skipped (stream output is unchanged).
3. **Config**
   - All config can be managed by admin APIs (global defaults + optional per-user overrides).
   - When model_uuid is not provided, resolution uses the earliest enabled config (by is_default then created_at): user scope -> global scope; no settings fallback, raises if no DB config.
   - LLM calls go through **LiteLLM**.
   - Cost (USD) is estimated from LiteLLM reference pricing and stored per call and in stats.

### Supported providers

- Each provider uses a smallest/cheapest default model to reduce
  misconfiguration cost.
- You can override `model` and optionally `api_base`/`deployment`
  in `config`.
- **All providers support `api_base` (URL)**:
  - official endpoint when omitted
  - proxy/forwarding URL when needed

| Provider        | Default model / notes |
|-----------------|------------------------|
| `openai`        | gpt-4o-mini (official default URL) |
| `azure_openai`  | gpt-4o-mini (requires `api_base` and `deployment`) |
| `gemini`        | gemini-2.0-flash |
| `anthropic`     | claude-3-5-haiku |
| `mistral`       | mistral-tiny |
| `dashscope`     | qwen-turbo (Alibaba Qwen) |
| `deepseek`      | deepseek-chat |
| `xai`           | grok-3-mini-beta (Grok) |
| `meta_llama`    | Llama-3.3-8B-Instruct |
| `amazon_nova`   | nova-micro-v1 |
| `nvidia_nim`    | meta/llama3-8b (Nemotron / NIM) |
| `minimax`       | MiniMax-M2.1 |
| `moonshot`      | moonshot-v1-8k (Kimi) |
| `zai`           | glm-4.5-flash (Z.AI GLM) |
| `volcengine`    | doubao-pro-32k (ByteDance Doubao) |
| `openrouter`    | google/gemma-2-9b-it:free |

- Config is from DB only (admin API); no Django settings fallback. At least one enabled global or user config is required for calls.

---

## API reference

- Mount under an admin prefix (e.g. `api/v1/admin/`).
- **Auth**: `IsAdminUser` (staff or superuser), otherwise 403.
- If the main project uses drf-spectacular, endpoints appear in
  Swagger UI (e.g. `/swagger`) under **llm-metering**.

### LLM configuration (global and per-user)

| Method | Path | Description |
|--------|------|-------------|
| GET | `.../llm-config/` | List global LLM configs (ordered by created_at, id) |
| POST | `.../llm-config/` | Create one config. Body: `provider`, `config` (optional `scope`, `user_id`, `is_active`) |
| GET | `.../llm-config/all/` | List all LLM configs (global + user). Optional `scope=all|global|user`, `user_id` |
| GET | `.../llm-config/<pk>/` | Get one config by id |
| PUT | `.../llm-config/<pk>/` | Update one config by id |
| DELETE | `.../llm-config/<pk>/` | Delete one config by id |
| GET | `.../llm-config/providers/` | Per-provider param schema (required/optional/editable keys, default model and api_base) for building provider-specific forms |
| GET | `.../llm-config/models/` | Provider list and model list with capability tags (text-to-text / vision / code / reasoning, etc.) |
| POST | `.../llm-config/test/` | Validate credentials without saving. Body: `provider`, `config` |
| POST | `.../llm-config/test-call/` | Run one completion and persist usage. Body: `config_uuid` (or legacy `config_id`), `prompt`, optional `max_tokens`, optional `stream` (see below) |
| GET | `.../llm-config/users/` | List per-user configs (optional `?user_id=` filter) |
| GET | `.../llm-config/users/<user_id>/` | Get one user's config (404 if not set) |
| PUT | `.../llm-config/users/<user_id>/` | Create or update that user's config |
| DELETE | `.../llm-config/users/<user_id>/` | Remove user config (they fall back to global default) |

- **POST/PUT body**
  - `provider` (default `openai`)
  - `config` (single JSON object, e.g. `api_key`, `model`, `api_base`,
    `deployment`, `max_tokens`, `temperature`, `top_p`)
  - for create/list workflows: optional `scope`, `user_id`, `is_active`,
    optional `model_type`
  - required/optional keys differ by provider (e.g. Azure needs
    `api_base` and `deployment`)
  - use `GET .../llm-config/providers/` to fetch schema
  - on GET, `config.api_key` and `config.key` are masked (e.g. `sk-**xxxx`); `is_default` is true when this config is the current default (earliest enabled global config used when model_uuid is not set), so the frontend can highlight the default model.

- **GET `.../llm-config/providers/`**
  - returns `{ "providers": { "<provider>": { "required": [...], "optional": [...], "editable_params": [...], "default_model": "...", "default_api_base": "..." } } }`
  - use it to render provider-specific forms and placeholders

- **POST `.../llm-config/test/`**
  - body: `provider`, `config` (same as PUT)
  - runs a minimal completion to verify key and endpoint
  - success: `200` + `{ "ok": true }`
  - validation/completion failure: `200` + `{ "ok": false, "detail": "..." }`
  - invalid payload: `400`

- **POST `.../llm-config/test-call/`**
  - body: `config_uuid` (preferred) or legacy `config_id`, `prompt`, optional `max_tokens` (default 512, max 4096), optional `stream` (default false)
  - when `stream` is false (default): JSON response. success: `{ "ok": true, "content": "...", "usage": { ... } }`; failure: `{ "ok": false, "detail": "..." }`
  - when `stream` is true: response is SSE (`Content-Type: text/event-stream`). Events: `data: {"type":"chunk","content":"<fragment>"}` for each content fragment; final event `data: {"type":"done","ok":true,"usage":{...}}` or `data: {"type":"done","ok":false,"detail":"..."}`
  - call is persisted to usage records; streaming calls are recorded with `is_streaming=true` and optional TTFT (`first_chunk_at`)

### GET `.../token-stats/`

- Returns aggregates and optional time series.
- Query params are all optional:

| Param        | Type   | Description |
|--------------|--------|-------------|
| start_date   | string | Start time, ISO or date-only (e.g. 2025-01-01) |
| end_date     | string | End time; date-only is end of that day |
| user_id      | int    | Filter by user id |
| granularity  | string | Time bucket: `day` (hour), `month` (day), `year` (month); omit for no series |
| use_series   | string | `1` / `true` / `yes`: when set with granularity and date range, also return `series_by_model` from pre-aggregated LLMUsageSeries (for per-model trend charts) |

**200** (JSON):

```json
{
  "summary": { ... },
  "by_model": [ ... ],
  "series": null,
  "series_by_model": null
}
```

- `series` is non-null only when `granularity` is set:
  `{ "granularity": "day", "items": [ { "bucket": "...", "total_tokens": 0, ... } ] }`
- `series_by_model` is non-null only when `use_series=1` (or `true`/`yes`) and `granularity` and `start_date`/`end_date` are set. It is a list of `{ "bucket", "model", "call_count", "success_count", "avg_e2e_latency_sec", "avg_ttft_sec", "avg_output_tps", "total_prompt_tokens", "total_completion_tokens", "total_tokens", "total_cached_tokens", "total_reasoning_tokens", "total_cost", "cost_currency" }` from the pre-aggregated table (global scope; not filtered by `user_id`). Use it for “Token trend by model” and “Cost trend by model” charts.
- invalid `granularity` returns `400` + `{ "detail": "..." }`

---

### GET / PATCH `.../metering-config/`

- **GET**: Returns effective metering config (retention, cleanup and aggregation schedules).
- **PATCH**: Update config. Body fields are optional: `retention_days` (1–3650), `cleanup_enabled`, `cleanup_crontab`, `aggregation_crontab` (five-field cron expressions).

**GET 200** (JSON):

```json
{
  "retention_days": 365,
  "cleanup_enabled": true,
  "cleanup_crontab": "0 2 * * *",
  "aggregation_crontab": "5 * * * *"
}
```

- Used by the admin UI “Data settings” / “Scheduled tasks” page to configure how long to keep data and when cleanup/aggregation run.

---

### GET `.../llm-usage/`

- Returns a paginated usage list.
- Query params:

| Param      | Type   | Description |
|------------|--------|-------------|
| page       | int    | Page number, default 1 |
| page_size  | int    | Page size, default 20, max 100 |
| user_id    | int    | Filter by user id |
| model      | string | Model name (icontains) |
| success    | string | `true` / `false` |
| start_date | string | Start time |
| end_date   | string | End time |

**200** (JSON):

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

- **UX**
  - use `token-stats` for dashboards and trend charts
  - use `llm-usage` for filterable, paginated call logs

---

## Pre-aggregated series (LLMUsageSeries)

- **Table**: `llm_usage_series` stores pre-aggregated usage per **(granularity, bucket, model)**. Granularities: `hour` (for “day” view), `day` (for “month” view), `month` (for “year” view).
- **Fields per row**: `bucket`, `model`, `call_count`, `success_count`, `avg_e2e_latency_sec`, `avg_ttft_sec`, `avg_output_tps`, token totals (`total_prompt_tokens`, `total_completion_tokens`, `total_tokens`, `total_cached_tokens`, `total_reasoning_tokens`), `total_cost`, `cost_currency`.
- **Population**: Celery task `aggregate_llm_usage_series_task` (hour + day + month in one run when invoked from beat) aggregates from `llm_tracker_usage` into `llm_usage_series`. Use it for fast “by model” trend charts without querying raw usage on each request.
- **API**: `GET .../token-stats/?use_series=1&granularity=...&start_date=...&end_date=...` returns `series_by_model` (list of the above rows) for charting.

---

## Metering config and scheduled tasks

- **Config model**: `MeteringConfig` (single row) holds `retention_days` (default 365), `cleanup_enabled`, `cleanup_crontab`, `aggregation_crontab`. API: `GET` / `PATCH` `.../metering-config/` (see above).
- **Celery tasks** (require Celery and `agentcore-task`; registered with django-celery-beat):
  - **Cleanup**: `cleanup_old_llm_usage_task` — deletes `llm_tracker_usage` and `llm_usage_series` older than `retention_days`. No-op if `cleanup_enabled` is false.
  - **Aggregation**: `aggregate_llm_usage_series_task` — runs hour, day, and month aggregation in one go (when called from beat without args); populates `llm_usage_series`.
- **Task tracking**: Both tasks register with **agentcore-task** `TaskTracker` (module `agentcore_metering`). Executions appear in the unified task list and stats (status, result, error).

---

## Data and layout

- **Tables**: `llm_tracker_usage` (usage records), `llm_usage_series` (pre-aggregated series), `agentcore_metering_llm_config` (LLM provider config), `MeteringConfig` (retention and cron settings).
- **Package**: `agentcore_metering.adapters.django` is a full Django app (models, views, urls, admin, migrations). The public API for LLM metering lives under `trackers/` (e.g. `trackers/llm.py`); import `LLMTracker` from `agentcore_metering.adapters.django` or `agentcore_metering.adapters.django.trackers.llm`. Additional tracker types may be added under `trackers/` (e.g. `trackers/other.py`).
