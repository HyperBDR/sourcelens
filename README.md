<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="frontend/public/brand/logo_with_text_dark.png">
  <img alt="SourceLens" src="frontend/public/brand/logo_with_text_transparent.png" width="320">
</picture>

[English](README.md) | [中文](README.zh-CN.md)

</div>

**SourceLens** is a file-system-native retrieval engine that leverages AI coding agents (Claude Code, Codex, etc.) to search, understand, and answer questions from local documents and codebases. It runs inside a sandboxed environment, making it a reliable retrieval backend for RAG pipelines.

## How It Works

```
User selects documents / code
        │
        ▼
  Local file system storage
        │
        ▼
  Pre-retrieval LLM processing ── query understanding, context planning
        │
        ▼
  Sandboxed AI agent retrieval ── Claude Code / Codex search & analyze
        │
        ▼
  Post-retrieval LLM processing ── answer synthesis, citation formatting
        │
        ▼
  Structured answer with source references
```

Instead of vector embeddings or keyword indexes, SourceLens uses AI coding agents running in a sandbox to directly read, navigate, and reason over the file system. This means the retrieval understands code structure, cross-file relationships, and semantic intent — not just surface-level text matching.

## Why SourceLens

- **AI-native retrieval** — leverages Claude Code and Codex as the retrieval engine, no vector DB required
- **Sandboxed execution** — all agent operations run in isolated environments, safe for arbitrary codebases
- **Pre/post LLM orchestration** — customizable LLM steps before and after retrieval for query refinement and answer synthesis
- **Source-traceable** — every answer references exact file paths and code locations
- **Works with any format** — documents (md, txt, pdf) and code (py, js, ts, vue, go, etc.)

## Typical Use Cases

| Scenario | Description |
|---|---|
| **Code Q&A** | Ask natural-language questions about large codebases, get precise answers with file references |
| **Document retrieval** | Search across project docs, API specs, and design documents in one query |
| **RAG pipeline backend** | Serve as the retrieval layer for LLM applications needing private knowledge |
| **Code review assist** | Find related changes and similar patterns across the repository |
| **Onboarding** | New team members explore code structure and business logic via natural language |

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

## Tech Stack

**Backend**: Python · Django REST Framework · Celery · PostgreSQL  
**Frontend**: Vue 3 · Vite · Pinia · Vue Router · Tailwind CSS · vue-i18n  
**Infra**: Docker · Nginx · Redis  

## Design Principles

Each Django app is self-contained (models, views, serializers, services, migrations, tests). Apps communicate via APIs. See [docs/DESIGN_PRINCIPLES.md](docs/DESIGN_PRINCIPLES.md).
