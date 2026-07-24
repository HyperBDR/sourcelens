<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="frontend/public/brand/logo_with_text_dark.png">
  <img alt="SourceLens" src="frontend/public/brand/logo_with_text_transparent.png" width="320">
</picture>

[English](README.md) | [中文](README.zh-CN.md)

**Harness-based Agentic RAG** — no embeddings, no vector DB, no pre-indexing

</div>

**SourceLens** is Agentic RAG built on an AI coding agent harness — the same kind of harness behind tools like Cursor, Claude Code, or Codex, not those products themselves — running inside a sandboxed environment. Instead of embedding your files into a vector index ahead of time, SourceLens hands them directly to the agent harness, which reads, searches, and reasons over the file system on demand — turning any pile of documents or code into something you can just ask questions of.

![What is SourceLens](docs/images/what_is_sourcelens.png)

Instead of vector embeddings or keyword indexes, SourceLens uses AI coding agents running in a sandbox to directly read, navigate, and reason over the file system. This means the retrieval understands code structure, cross-file relationships, and semantic intent — not just surface-level text matching.

## Background

Our first attempts at RAG used graphical workflow tools like Dify and n8n. They asked a lot of the people building on them, and the real difficulty was always upfront: splitting documents and embedding them before they ever reached a vector store. That prep work took real effort to get right, and even after all of it, recall accuracy stayed disappointing — answers would come back incomplete, sometimes missing the point that was in the document all along.

Around the same time, we noticed something different from using Cursor for development: it did no pre-training or pre-indexing at all, yet it was consistently accurate at reasoning over a codebase. That raised an obvious question — why not use the same approach for RAG?

That's the idea behind SourceLens: instead of the embed-then-retrieve pipeline, hand documents and code straight to an AI coding agent harness — the same kind of logic behind Cursor, Claude Code, or Codex — and let it read and reason over them directly. In practice we've found the answers come back more accurate, more precise, and more concise than what the traditional RAG pipeline produced, and that experience is what turned into this project.

Most teams building a RAG knowledge base today go through some version of this same graphical-orchestration pipeline — tools like Dify, n8n, Coze, or FastGPT, wired up to a vector store. SourceLens's core goal is to drive the cost of standing up a working RAG system as close to zero as possible, without trading away answer quality.

The underlying loop stays deliberately simple: a query triggers the agent to search, it synthesizes what it finds into a partial answer, and if that's not enough, it searches again and synthesizes again — repeating until it can answer with confidence. Skills and MCP integration are the planned path for extending what the agent can reach beyond the local file system, without changing that core loop.

## Why SourceLens

- **Agentic RAG, not embeddings** — an agent harness (the same kind behind Cursor, Claude Code, Codex, etc.) reads and reasons over files directly, no vector DB, no pre-indexing step
- **Sandboxed execution** — all agent operations run in isolated environments, safe for arbitrary codebases and documents
- **Pre/post LLM orchestration** — customizable LLM steps before and after retrieval for query refinement and answer synthesis
- **Source-traceable** — every answer references exact file paths and code locations
- **Works with any format** — Markdown, Word, PPT, images, and code (py, js, ts, vue, go, etc.), with zero prep

## Use Cases

Three scenarios from how we use SourceLens internally today:

### 1. RAG over documents — no embedding step required

Point SourceLens at documents in any of these formats and start asking questions immediately — no pre-indexing, no embedding pipeline to run first:

- Markdown exported from online docs platforms (e.g. ViewPress)
- Word documents
- PowerPoint decks
- Content inside images

### 2. Deep code insight from a screenshot

Hit an error? Paste a screenshot of it and let the agent harness trace it back through the actual source — a deep, source-level investigation instead of just matching the error string.

### 3. Company-wide Skills as a universal chat interface

We package internal engineering knowledge as company-level Skills that anyone can use to find and diagnose problems, exposed as one universal chat mode:

- **No install** — nothing to set up in a local tool first
- **Answer online** — ask in a chat session and get the answer directly
- **Generate & download** — the same session can generate a file and hand it back to you

> Also fun in testing: pointing the same deep-insight flow at long-form content like novels turns out to be a surprisingly effective way to explore and query them.

## Architecture

```
sourcelens/
├── backend/                    # Django REST API
│   ├── core/                   # Project config (settings/, urls.py, celery.py)
│   ├── accounts/               # Auth, roles, permissions
│   └── agentcore/              # Git submodules
│       ├── agentcore-metering/  # LLM usage tracking  → /api/v1/admin/
│       ├── agentcore-task/      # Unified task mgmt     → /api/v1/tasks/
│       └── agentcore-notifier/  # Notifications         → /api/v1/admin/notifications/
├── frontend/                   # Vue 3 (Vite + Pinia + Tailwind + vue-i18n)
└── docs/                       # Design docs
```

## Quick Start

### 1. Clone with submodules

```bash
git submodule update --init --recursive
```

### 2. Docker dev

```bash
cp env.sample .env.dev
# Edit .env.dev — database, AI service keys, etc.
docker-compose -f docker-compose.dev.yml up -d
```

### 3. Services

| Service | URL |
|---|---|
| Web UI | http://localhost:8000 |
| API Docs | http://localhost:8000/swagger/ |
| Admin | http://localhost:8000/admin/ |
| Flower | http://localhost:5555 |

### 4. Common Commands

```bash
# Backend
pytest
pytest path/to/test.py

# Django
python backend/manage.py migrate
python backend/manage.py register_periodic_tasks
python backend/manage.py createsuperuser

# Code quality
black --check backend/
isort --check backend/

# Frontend
cd frontend && npm install
npm run dev          # → http://localhost:5173
npm run build
npm run lint
npm run test:e2e     # Playwright E2E
```

## Agentcore Submodules

| Submodule | Django App | URL prefix |
|---|---|---|
| `agentcore-metering` | `agentcore_metering.adapters.django` | `/api/v1/admin/` |
| `agentcore-task` | `agentcore_task.adapters.django` | `/api/v1/tasks/` |
| `agentcore-notifier` | `agentcore_notifier.adapters.django` | `/api/v1/admin/notifications/` |

Local editable install:

```bash
for d in backend/agentcore/*/; do
  [ -f "${d}pyproject.toml" ] && pip install -e "$d"
done
```

## Celery Task System

- **Discovery**: `core/celery.py` calls `autodiscover_tasks()` to load `tasks.py` from every app
- **Periodic tasks**: Registered via `register_periodic_tasks` into `django_celery_beat`; existing records are never overwritten
- **Startup order**: `wait_for_db` → `migrate` → `register_periodic_tasks` → start service

## Production

```bash
cp env.sample .env
# Configure SECRET_KEY, DJANGO_DEBUG=false, ALLOWED_HOSTS, database, etc.
docker-compose up -d
```

Default ports: HTTP 10080, HTTPS 10443 (configurable via `NGINX_HTTP_PORT` / `NGINX_HTTPS_PORT`).

### Capacity & Concurrency Tuning

Production serves many users, so size these in the server `.env` (CI never overwrites `.env`, so values persist across deploys):

| Variable | Controls | Default | Guidance |
|---|---|---|---|
| `LENSNODE_MAX_CONCURRENT_RUNS` | Concurrent answer runs on a LensNode | `1` | **The real throughput cap — raise it.** When the node is full a run sits in `Queued` (retried every 5s, up to 120s). Set it ≥ the busiest assistant's `max_concurrency`, sized to RAM (each deep-agent run uses hundreds of MB) and upstream LLM rate limits. |
| `CELERY_CONCURRENCY` | Celery worker processes | CPU count | Rarely the bottleneck: worker tasks just dispatch to the LensNode (the heavy work runs there). A modest bump only adds headroom. |
| `max_concurrency` (per assistant, DB) | Concurrent runs per assistant | `5` | Per-assistant limit; the system-wide cap is `LENSNODE_MAX_CONCURRENT_RUNS`. |

- The API runs as a **single Daphne ASGI process** (one core). Async handles many concurrent connections, but using more cores means running multiple ASGI workers/replicas — not an `.env` change.
- Use **Docker Compose v2** (`docker compose`) on the server. Legacy v1 (`docker-compose`) aborts `up -d` on `build:` contexts the deploy does not ship to the host.
- `.env` changes need a recreate, not a restart (`docker restart` does not re-read env files):

  ```bash
  APP_VERSION=<version> docker compose up -d --force-recreate --no-deps lensnode backend-worker
  ```

## Tech Stack

**Backend**: Python · Django REST Framework · Celery · PostgreSQL  
**Frontend**: Vue 3 · Vite · Pinia · Vue Router · Tailwind CSS · vue-i18n  
**Infra**: Docker · Nginx · Redis  

## Design Principles

Each Django app is self-contained (models, views, serializers, services, migrations, tests). Apps communicate via APIs. See [docs/DESIGN_PRINCIPLES.md](docs/DESIGN_PRINCIPLES.md).
