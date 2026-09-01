# 设计稿：内置集成 Plugin（Tool + Datasource）

- 状态：设计讨论中（未开始开发）
- 日期：2026-09-01
- 范围：GitHub、GitLab、Jira 等内置集成；同时服务代码数据源和助手工具。

## 1. 背景与问题

当前 GitHub、GitLab、Jira 能力主要以可上传的 CLI/Skill 形式存在。凭证被建模为
DataSource 的附属对象，无法自然复用于 Skill 和 MCP；Skill 还需要自行处理 CLI
参数、第三方 API 和 secret，导致授权、审计、动态配置和错误处理分散。

Dify 的 Plugin Provider 模型验证了另一条路径：一个插件可以同时注册 Tool
Provider 和 Datasource Provider，平台根据插件声明动态展示配置并负责调用路由。
SourceLens 采用这一方向，但增加独立的 Connection、Capability 和版本化授权层，
避免把原始凭证无条件传给插件进程。

## 2. 目标与非目标

### 目标

- 将现有管理 CLI 封装为 GitHub、GitLab、Jira 等内置 Plugin Runtime。
- 一个 Plugin 同时提供 DataSource 适配器和面向大模型的 Tool Provider。
- 凭证、连接目标、资源范围和消费者配置分层，支持真正复用。
- 管理页面由 Plugin manifest 动态生成，不硬编码每个供应商的表单。
- 支持 Plugin 内部并发请求第三方 API，并统一处理超时、限流、重试和取消。
- 对每次调用实施用户、Assistant、Skill、Connection、Capability 和资源范围校验。
- 保留现有 CLI 作为底层执行器，逐步迁移到统一 Plugin 协议。

### 非目标

- 第一阶段不开放任意第三方 Python/原生插件执行平台权限。
- 第一阶段不允许普通上传 Skill 直接读取长期 Token。
- 不把所有 CLI 子命令原样暴露给模型。
- 不在本设计中解决多租户产品模型之外的组织身份同步。

## 3. 核心概念

```text
PluginDefinition
  ├─ ToolProvider
  ├─ DatasourceProvider
  ├─ credential_schema / connection_schema
  ├─ capabilities
  └─ runtime_adapter

SecretMaterial ──< SecretVersion
Connection ──────── references one SecretVersion
  ├─ endpoint / tenant / audience
  ├─ allowed scopes
  └─ grants / status

DataSource / Skill / MCP
  └─ binds Connection and declares required capabilities
```

### Plugin

代表一个外部系统集成，如 `github`、`gitlab`、`jira`。Plugin 注册协议、能力、
动态配置 schema 和运行时适配器。

### SecretMaterial

只保存加密的 Token、App Secret、OAuth refresh token 等秘密材料，并支持版本、轮换、
撤销和状态。它不包含仓库、项目或文件夹范围。

### Connection

代表可以被消费者使用的完整连接：Plugin、endpoint/tenant/audience、非敏感配置、
允许范围、SecretVersion 和授权关系。DataSource、Skill、MCP 绑定 Connection，而不
直接绑定 SecretMaterial。

### Capability

描述最小业务权限，例如：

- `repository.read`
- `pull_request.read`
- `issue.read`
- `issue.write`
- `jira.issue.search`
- `jira.issue.transition`

Capability 同时用于 UI 展示、绑定校验、运行时授权、风险分级和审计。

## 4. Plugin Manifest

Manifest 是平台可读的稳定契约，不是安全边界。建议结构如下：

```yaml
key: github
version: 1.0.0
display_name: GitHub
description: Access authorized GitHub repositories and pull requests.

connection_schema:
  fields:
    - key: endpoint
      type: url
      required: true
    - key: tenant
      type: string
      required: false
    - key: token
      type: secret
      required: true

capabilities:
  - key: repository.read
    risk: low
  - key: pull_request.read
    risk: low
  - key: issue.write
    risk: high
    confirmation_required: true

datasource:
  supported: true
  resources: [organization, repository, branch]

tools:
  - key: github_read_file
    capability: repository.read
    side_effect: none
  - key: github_search_code
    capability: repository.read
    side_effect: none
  - key: github_create_issue
    capability: issue.write
    side_effect: write
```

Manifest 应包含：

- 身份、版本、展示名称、图标和说明；
- credential/connection 字段类型、默认值、校验和脱敏规则；
- capability、风险等级、读写属性和是否需要确认；
- DataSource 资源发现与同步声明；
- Tool 名称、描述、输入/输出 JSON Schema 和所需 capability；
- 运行时版本和兼容的 CLI/API 协议版本。

动态页面只使用 schema 生成表单；后端必须再次执行完整校验。

## 5. Tool Provider 设计

Plugin Tool 是给大模型调用的原子业务工具，不是 CLI passthrough。

```json
{
  "name": "github_read_file",
  "description": "Read a text file from an authorized GitHub repository. "
                 "Do not use this tool to modify files.",
  "input_schema": {
    "type": "object",
    "properties": {
      "repository": {"type": "string"},
      "path": {"type": "string"},
      "ref": {"type": "string"}
    },
    "required": ["repository", "path"]
  }
}
```

运行路径：

```text
LLM tool call
  → Tool Gateway
  → 校验 actor / Assistant / Skill / Connection / capability / resource
  → Plugin Runtime
  → CLI 或第三方 API
  → 结果清洗、大小限制和敏感信息过滤
  → Tool result 返回模型
```

禁止提供 `github_raw_exec(command)` 之类的通用命令工具。写操作必须有独立
capability、幂等键和按风险配置的用户确认或审批。

Skill 可以保留流程说明，但只声明依赖：

```yaml
required_plugins:
  - plugin: github
    capabilities: [repository.read, pull_request.read]
```

Skill 负责告诉模型如何组合工具，Plugin Tool 负责实际访问外部系统。

## 6. Datasource Provider 设计

Datasource Provider 面向资源发现、内容摄取和增量同步，不直接复用 Tool 的业务
流程。

```text
DataSource
  - plugin: github
  - connection: github-company-readonly
  - resource: HyperBDR/sourcelens
  - branch: main
  - sync policy

Plugin Datasource Provider
  ├─ discover organizations / repositories / branches
  ├─ validate connection and resource scope
  ├─ fetch repository content
  ├─ report progress
  └─ return files / metadata for indexing
```

同一个 GitHub Connection 可以服务多个 DataSource；每个 DataSource 独立保存仓库、
分支、目录和同步策略，不能反向修改 Connection 的 endpoint 或 secret scope。

## 7. MCP 集成

MCP 可以作为 Plugin 的另一种工具呈现方式：

- Plugin Tool 适合平台原生、稳定且需要强约束的工具；
- MCP 适合外部工具集合或已有 MCP Server；
- 两者共享 Connection、Capability、授权和审计；
- MCP Server 不能通过任意 header 直接绕过 Connection 校验。

```text
Plugin Connection
  ├─ Native Tool Provider
  └─ MCP Adapter
```

## 8. 凭证与运行时安全

### 8.1 连接和凭证分离

GitHub PAT 不包含仓库 URL；Jira Token 不包含项目选择。Connection 才绑定
endpoint、tenant、audience 和允许范围。

### 8.2 Secret 交付

默认采用：

```text
Plugin Runtime → 短期 Connection lease → Provider API/CLI
```

普通 Skill 只获得工具，不获得原始 Token。受信任的内置 Plugin 可以在受限 Runtime
中使用 lease；lease 绑定用户、Run、Plugin、Capability、资源范围和过期时间。

### 8.3 强制校验

每次调用必须校验：

1. 当前用户和有效 actor；
2. Assistant/Skill 是否允许使用该 Plugin；
3. Connection 是否属于当前租户且状态有效；
4. Capability 是否满足；
5. endpoint、仓库、项目或文件夹是否在允许范围；
6. 工具读写级别、确认和速率限制；
7. lease、SecretVersion 和 Plugin manifest 是否仍有效。

说明文字不是安全边界，所有约束必须在执行器中落实。

## 9. Plugin 内部并发与异步

工具对模型可以同步返回，但 Plugin 内部可以并行请求：

```text
github_get_pull_request_context
  ├─ pull request metadata
  ├─ changed files
  ├─ reviews
  └─ comments
```

建议 Runtime 提供统一的 `PluginRequestContext`：

- async HTTP client 和连接池；
- 每次调用和每个 Connection 的并发上限；
- deadline、取消传播和重试策略；
- Provider rate-limit budget；
- correlation ID 和脱敏日志。

只读、互相独立的请求可使用 `asyncio.gather`/任务组并行；写操作和有依赖的请求
必须保持顺序。部分失败应返回可用结果与结构化 warning，而不是静默丢失上下文。

长任务（大仓库同步、批量导出）使用平台任务系统并流式报告进度；短任务内部并行后
一次性返回给模型。

## 10. 现有 CLI 的复用方式

第一阶段不重写 CLI：

```text
GitHub Plugin Runtime
  ├─ Tool adapter → 受限 CLI 子命令或 API
  └─ Datasource adapter → 现有代码同步 CLI
```

适配器负责：

- 将结构化工具参数转换为固定 CLI 参数；
- 禁止 shell 拼接和任意命令；
- 注入短期认证上下文；
- 限制工作目录、网络和文件输出；
- 将 stdout/stderr 转为脱敏的结构化结果和进度事件。

对于 GitHub/GitLab/Jira 的标准 HTTP API，优先在 Plugin Runtime 使用异步 HTTP
客户端；CLI 保留给已有复杂流程或必须复用的同步实现。

## 11. API 与数据模型草案

建议新增：

```text
PluginDefinition
PluginVersion
SecretMaterial
SecretVersion
Connection
ConnectionGrant
PluginToolBinding
PluginDatasourceBinding
PluginInvocation
```

建议 API：

```text
GET  /api/lens/admin/plugins/
GET  /api/lens/admin/plugins/{key}/manifest/
GET  /api/lens/admin/plugins/{key}/tools/
GET  /api/lens/admin/plugins/{key}/datasources/

GET  /api/lens/admin/connections/
POST /api/lens/admin/connections/
PATCH /api/lens/admin/connections/{uuid}/
POST /api/lens/admin/connections/{uuid}/validate/
POST /api/lens/admin/connections/{uuid}/rotate/
POST /api/lens/plugin-tools/{provider}/{tool}/invoke/
```

持久化 Run 只记录 Plugin、Connection、SecretVersion、Capability 和资源引用，
不记录解析后的 secret。

## 12. 迁移路径

### Phase 1：协议和内置 GitHub Plugin

- 定义 manifest、capability 和 Tool/Datasource Provider 接口；
- 将现有 GitHub CLI 封装成 Plugin Runtime；
- 跑通 Connection → DataSource 同步；
- 跑通 `github_read_file`、`github_search_code` 等只读工具；
- 保留旧 DataSourceCredential 读路径，但禁止新功能继续扩展旧模型。

### Phase 2：GitLab、Jira 与动态管理页

- 增加 GitLab/Jira 内置 Plugin；
- 根据 manifest 动态渲染 Connection 页面；
- 增加资源发现、能力筛选和绑定校验；
- 将现有 GitHub/GitLab/Jira Skills 改为流程 Skill，移除自行读取 Token 和执行
  任意 CLI 的逻辑。

### Phase 3：凭证版本和安全运行时

- 引入 SecretVersion、lease、轮换和撤销；
- PluginInvocation 审计；
- 工具读写风险策略、确认和审批；
- MCP 通过同一 Connection/Capability 层接入。

### Phase 4：兼容迁移和清理

- 将旧 DataSourceCredential 映射为 Connection；
- 校验并修正 endpoint/scope；
- 提供失败可回滚的双读迁移；
- 删除旧的 DataSourceCredential API 和明文 Reveal 能力。

## 13. 主要风险与取舍

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| Plugin 代码取得原始 secret | 高 | 内置受信任 Runtime、短期 lease、最小权限 |
| 动态 schema 过于复杂 | 中 | 第一阶段限制字段类型，保留少量自定义组件 |
| CLI 参数被模型注入 | 高 | 只暴露业务工具，固定参数映射，禁止 raw exec |
| 第三方 API 限流 | 中 | Connection/provider 并发预算、Retry-After、退避 |
| 旧凭证迁移失败 | 高 | 双读、版本化、回滚和迁移前 scope 校验 |
| Tool 与 Datasource 语义混淆 | 中 | 两套 Provider 接口，共享 Connection 但分离执行契约 |
| 插件版本改变权限 | 高 | manifest 版本、能力变更重新验证和重新审批 |

## 14. 验收标准

- GitHub Plugin 可以同时出现在 DataSource 和 Skill 工具选择流程中；
- 同一个 Connection 可绑定多个 DataSource 和多个 Skill/MCP；
- 管理页面只依赖 manifest，不写 GitHub/Jira 专用分支；
- 模型只能看到已授权 capability 对应的工具；
- Plugin 内部可并行读取多个 API，且有并发上限、超时、取消和部分失败结果；
- 原始 secret 不进入 prompt、Tool 参数、Run 快照和普通日志；
- 写操作具备独立 capability、幂等和确认/审批策略；
- 现有 CLI 能在不改变业务行为的情况下作为 Plugin Runtime 后端执行器。

## 15. 待确认问题

1. 第一阶段 Connection 是否只允许管理员创建和授权？
2. 内置 Plugin 的运行位置是控制端、LensNode，还是按操作类型分别选择？
3. GitHub/GitLab 的资源 scope 是 Connection 级限制，还是允许 DataSource 级细化？
4. Jira 是否同时支持 Cloud OAuth、PAT 和 Server/Data Center Basic Auth？
5. Skill 工具调用是否默认允许读操作，写操作统一需要用户确认？
6. 是否先实现原始 secret 的受信任 CLI 注入，再逐步迁移到短期 token lease？
