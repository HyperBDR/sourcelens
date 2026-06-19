<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="frontend/public/brand/logo_with_text_dark.png">
  <img alt="SourceLens" src="frontend/public/brand/logo_with_text_transparent.png" width="320">
</picture>

中文 | [English](README.md)

</div>

**SourceLens** 是一款基于文件系统的检索引擎。它利用 AI 编程工具（Claude Code、Codex 等）在沙箱中对本地文档和代码仓库进行检索、理解和问答，可作为 RAG 管道的可靠 retrieval 后端。

## 工作流程

```
用户选择文档 / 代码
        │
        ▼
  本地文件系统存储
        │
        ▼
  检索前 LLM 处理 ── 查询理解、上下文规划
        │
        ▼
  沙箱内 AI agent 检索 ── Claude Code / Codex 搜索与分析
        │
        ▼
  检索后 LLM 处理 ── 答案整合、引用格式化
        │
        ▼
  带来源引用的结构化答案
```

区别于向量嵌入或关键词索引，SourceLens 让 AI 编程 agent 在沙箱中直接读取、导航和推理文件系统。这意味着检索过程能够理解代码结构、跨文件关系和语义意图，而非仅停留在表层文本匹配。

## 为什么选择 SourceLens

- **AI 原生检索** — 以 Claude Code、Codex 作为检索引擎，无需向量数据库
- **沙箱隔离执行** — 所有 agent 操作在隔离环境中运行，安全处理任意代码仓库
- **LLM 前后置编排** — 检索前后可配置 LLM 步骤，优化查询理解与答案合成
- **来源可追溯** — 每个答案精确关联到源文件路径和代码位置
- **任意格式** — 支持文档（md, txt, pdf）和代码（py, js, ts, vue, go 等）

## 典型使用场景

| 场景 | 说明 |
|---|---|
| **代码问答** | 用自然语言对大型代码仓库提问，获取带文件引用的精准答案 |
| **文档检索** | 跨项目文档、API 规格、设计文档统一检索 |
| **RAG 管道后端** | 作为 LLM 应用的私有知识库 retrieval 层 |
| **代码审查辅助** | 在仓库中检索相关变更和相似代码片段 |
| **新人上手** | 新成员通过自然语言探索代码结构和业务逻辑 |

## 架构总览

```
sourcelens/
├── backend/                    # Django REST API
│   ├── core/                   # 项目配置（settings/、urls.py、celery.py）
│   ├── accounts/               # 用户认证、权限与角色管理
│   └── agentcore/              # Git 子模块
│       ├── agentcore-metering/  # LLM 用量追踪  → /api/v1/admin/
│       ├── agentcore-task/      # 统一任务管理   → /api/v1/tasks/
│       └── agentcore-notifier/  # 通知服务       → /api/v1/admin/notifications/
├── frontend/                   # Vue 3（Vite + Pinia + Tailwind + vue-i18n）
└── docs/                       # 设计文档
```

## 快速上手

### 1. 拉取子模块

```bash
git submodule update --init --recursive
```

### 2. Docker 本地开发

```bash
cp env.sample .env.dev
# 按需编辑 .env.dev，配置数据库、AI 服务密钥等
docker-compose -f docker-compose.dev.yml up -d
```

### 3. 访问服务

| 服务 | 地址 |
|---|---|
| Web UI | http://localhost:8000 |
| API 文档 | http://localhost:8000/swagger/ |
| 管理后台 | http://localhost:8000/admin/ |
| Flower | http://localhost:5555 |

### 4. 常用命令

```bash
# 后端测试
pytest
pytest path/to/test.py

# Django 管理
python backend/manage.py migrate
python backend/manage.py register_periodic_tasks
python backend/manage.py createsuperuser

# 代码质量
black --check backend/
isort --check backend/

# 前端
cd frontend && npm install
npm run dev          # → http://localhost:5173
npm run build
npm run lint
npm run test:e2e     # Playwright E2E
```

## Agentcore 子模块

| 子模块 | Django App | URL 前缀 |
|---|---|---|
| `agentcore-metering` | `agentcore_metering.adapters.django` | `/api/v1/admin/` |
| `agentcore-task` | `agentcore_task.adapters.django` | `/api/v1/tasks/` |
| `agentcore-notifier` | `agentcore_notifier.adapters.django` | `/api/v1/admin/notifications/` |

本地可编辑安装：

```bash
for d in backend/agentcore/*/; do
  [ -f "${d}pyproject.toml" ] && pip install -e "$d"
done
```

## Celery 任务机制

- **任务发现**：`core/celery.py` 通过 `autodiscover_tasks()` 自动加载各 app 的 `tasks.py`
- **定时任务**：通过 `register_periodic_tasks` 写入 `django_celery_beat`，现有记录不会被覆盖
- **启动顺序**：`wait_for_db` → `migrate` → `register_periodic_tasks` → 启动服务

## 生产部署

```bash
cp env.sample .env
# 配置 SECRET_KEY、DJANGO_DEBUG=false、ALLOWED_HOSTS、数据库等
docker-compose up -d
```

默认端口：HTTP 10080, HTTPS 10443（可通过 `NGINX_HTTP_PORT`、`NGINX_HTTPS_PORT` 调整）。

### 容量与并发调优

生产面向多用户，按负载在服务器 `.env` 中调整这些值（CI 不会覆盖 `.env`，跨部署保留）：

| 变量 | 作用 | 默认 | 调优建议 |
|---|---|---|---|
| `LENSNODE_MAX_CONCURRENT_RUNS` | 单个 LensNode 的并发问答数 | `1` | **真正的吞吐上限——务必调大。** 节点满时新 run 会停在 `Queued`（每 5s 重试，最长 120s）。设为 ≥ 最繁忙助手的 `max_concurrency`，并按内存（每个 deep-agent 回答约数百 MB）与上游 LLM 限流量力而行。 |
| `CELERY_CONCURRENCY` | Celery worker 进程数 | CPU 核数 | 很少是瓶颈：worker 任务只是把活派发给 LensNode（重活在 LensNode 上跑）。适度上调只为留余量。 |
| `max_concurrency`（每助手，DB） | 单个助手的并发 run 数 | `5` | 按助手限流；系统级上限是 `LENSNODE_MAX_CONCURRENT_RUNS`。 |

- API 实为**单个 Daphne ASGI 进程**（只占 1 核）。async 能抗大量并发连接，但要用更多核需多开 ASGI worker/副本——不是 `.env` 能搞定的。
- 服务器上用 **Docker Compose v2**（`docker compose`）。旧版 v1（`docker-compose`）会因部署未下发的 `build:` 上下文而中止 `up -d`。
- 改完 `.env` 需重建而非重启（`docker restart` 不会重读 env 文件）：

  ```bash
  APP_VERSION=<version> docker compose up -d --force-recreate --no-deps lensnode backend-worker
  ```

## 技术栈

**后端**：Python · Django REST Framework · Celery · PostgreSQL  
**前端**：Vue 3 · Vite · Pinia · Vue Router · Tailwind CSS · vue-i18n  
**基础设施**：Docker · Nginx · Redis  

## 设计原则

每个 Django app 自包含（models、views、serializers、services、migrations、tests），app 之间通过 API 解耦。详见 [docs/DESIGN_PRINCIPLES.zh-CN.md](docs/DESIGN_PRINCIPLES.zh-CN.md)。
