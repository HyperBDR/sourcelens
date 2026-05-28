# Agentcore Metering — Design (English)

This document describes the design positioning, principles, and capabilities of Agentcore Metering for review and implementation alignment.

---

## 1. Positioning and goals

- **Positioning**: A unified **AI invocation and statistics module** for Django projects, providing observability for LLM calls (usage, cost, configuration).
- **Goals**: Use LiteLLM for unified completion and cost estimation; provide a config catalog (global and per-user), usage records, and statistics APIs; enable reuse across Newshub, Devify, easy-divine, devmind, and other projects, avoiding duplicated LLM tracking and configuration logic.

---

## 2. Scenarios and requirements

The module’s core capabilities fall into two **usage scenarios**:

- **Django projects and application code (recording side)**: Projects use the module via **import** in code (e.g. `LLMTracker.call_and_track(...)`) to implement **recording**—calls are persisted on invoke; sensitive data need not be kept in environment variables, and configuration is managed through a single entry point.
- **Administrators (API side)**: HTTP APIs are provided mainly for **administrator users** to **query and aggregate**—e.g. usage lists, aggregation by time/model/user, cost statistics, config management; regular users do not depend on these APIs directly.

The scenarios and requirements above are established first; the “core capabilities” section then elaborates the concrete capabilities.

---

## 3. Design principles

### 3.1 Observability as side-channel

- The module **only records** calls and usage; it does not drive business workflows.
- Application code invokes `LLMTracker.call_and_track(...)`; tracking and persistence are **side-channel**; business logic and LiteLLM remain the source of truth for invocation.

### 3.2 Configuration and usage are separate

- **Configuration**: LLM model, API, parameters, etc. are managed by a “config catalog” (global default + optional per-user overrides). Resolution order: user scope → global scope; DB only, no settings fallback.
- **Usage**: Each call produces one usage record (tokens, cost, model, user, etc.) for statistics and cost analysis; configuration and usage are not mixed in the same table or responsibility.

### 3.3 Cost and currency

- Cost is stored as **amount + currency** (e.g. `cost`, `cost_currency`).
- Default currency is USD (aligned with LiteLLM); supports future multi-currency or localized display.

### 3.4 Unified config entry (no sensitive data in environment variables)

- The module provides a **unified config entry** (management API + database storage). API keys, `api_base`, and other sensitive values are maintained via the config catalog and **do not need to be declared in environment variables**.
- Keys and endpoints that differ by environment (dev/staging/prod) or by user can all be managed through config, reducing exposure risk and deployment complexity.

---

## 4. Core capabilities

| Capability | Description |
|------------|-------------|
| **1. LLM invocation and tracking** | `LLMTracker.call_and_track(...)`: uses LiteLLM for completion and persists usage (tokens, cost, model, user, etc.); optional `state` (e.g. `user_id`) for per-user config. |
| **2. Config catalog** | Global default + per-user overrides; CRUD via a **unified config entry** (management API); sensitive data (e.g. API keys) live in the database, **not in env vars**; resolution is from DB only (user → global), no settings fallback. |
| **3. Usage records and statistics** | Each call writes to `LLMUsage`; APIs for time/model/user aggregation and paginated lists (e.g. token-stats, llm-usage). |
| **4. Multiple providers and models** | LiteLLM supports multiple providers; each can configure default model, `api_base`, etc.; cost is estimated from LiteLLM reference pricing. |

---

## 5. Out of scope

- Does not drive business flows or replace business-side prompt/workflow design.
- Does not perform billing or invoicing (only provides usage and cost data; billing is owned by the product or upstream systems).
- Does not provide “auto rate-limit/circuit-break by usage” (product or gateway can implement this using this module’s data).

---

## 6. Relationship to other projects

- **Shared needs**: All projects need “unified LLM invocation + configurable model/API + queryable usage and cost”.
- **Replaceable**: Per-project LLM config and usage recording can be replaced by this module; integration is done by registering the app, mounting URLs, and using `LLMTracker.call_and_track`.

---

## 7. Schema and storage

- **LLMUsage**: Single table for per-call usage (user, model, tokens, cost, cost_currency, success, etc.); filtering and aggregation by scalar columns meet listing and statistics needs. Call mode (streaming vs non-streaming) is persisted by the tracker (`is_streaming`); for streaming calls, TTFT (time to first token) is recorded via `first_chunk_at` and used as the primary latency in listing/statistics.
- **LLM config**: Config table(s) hold global and per-user config (model, api_base, parameters, etc.); resolution logic lives in the service layer and is separate from usage tables.

---

## 8. Related docs

- Design (Chinese): [DESIGN.zh-CN.md](DESIGN.zh-CN.md)
- Usage: [README.zh-CN.md](../README.zh-CN.md) / [README.md](../README.md)

---
