# 设计稿：内置集成 Plugin（Tool + Datasource）

- 状态：提议（V1 范围已收敛，未开始开发）
- 日期：2026-09-01
- 范围：GitHub、GitLab、Jira 等内置集成；同时服务代码数据源和助手工具。

本设计借鉴 Dify 的 Plugin Daemon、双 Provider 和 Manifest 机制，但不采用其在
调用请求中传递完整 credentials 的方式。Plugin 是商业化交付物，以独立项目构建和
发布，由企业部署安装；普通用户不能上传或安装 Plugin。

## 1. 背景与问题

当前 GitHub、GitLab、Jira 能力主要以可上传的 CLI/Skill 形式存在。凭证被建模为
DataSource 的附属对象，无法自然复用于 Skill 和 MCP；Skill 还需要自行处理 CLI
参数、第三方 API 和 secret，导致授权、审计、动态配置和错误处理分散。

Dify 的 Plugin Provider 模型验证了另一条路径：一个插件可以同时注册 Tool
Provider 和 Datasource Provider，平台根据插件声明动态展示配置并负责调用路由。
SourceLens 采用这一方向，但增加独立的 Connection、Capability 和受控运行时，避免
将原始凭证无条件传给 Skill、模型或任务消息。

## 2. 目标与非目标

### 目标

- 将现有管理 CLI 封装为 GitHub、GitLab、Jira 等内置 Plugin Runtime。
- 一个 Plugin 同时提供 DataSource 适配器和面向大模型的 Tool Provider。
- 凭证、连接目标、资源范围和消费者配置分层，支持真正复用。
- 管理页面由 Plugin manifest 动态生成，不硬编码每个供应商的表单。
- 改造数据源管理，使其通过 Connection 与 Plugin Provider 同步，而不再向 LensNode
  下发解密后的 credential config。
- 支持 Plugin 内部并发请求第三方 API，并统一处理超时、限流、重试和取消。
- 对每次调用实施用户、Assistant、Skill、Connection、Capability 和资源范围校验。
- V1 仅支持受信任内置 Plugin 提供的、代码圈定的只读操作。
- 保留现有 CLI 作为底层执行器，逐步迁移到统一 Plugin 协议。

### 非目标

- 第一阶段不开放任意第三方 Python/原生插件执行平台权限。
- 第一阶段不允许普通上传 Skill 直接读取长期 Token。
- 不把所有 CLI 子命令原样暴露给模型。
- 第一阶段不支持写操作、第三方可执行 Plugin 或通用 OAuth 流程。
- 不在本设计中解决多租户产品模型之外的组织身份同步。

## 3. 核心概念

```text
PluginDefinition
  ├─ ToolProvider
  ├─ DatasourceProvider
  ├─ credential_schema / connection_schema
  ├─ capabilities
  └─ runtime_adapter

PluginRegistry
  └─ discovers trusted installed Plugin projects and negotiated versions

SecretMaterial ──< SecretVersion
Connection ──────── references one SecretVersion
  ├─ endpoint / tenant / audience
  ├─ allowed scopes
  └─ grants / status

DataSource / Skill / MCP
  └─ binds Connection and declares required capabilities

ExecutionSnapshot
  └─ immutable configuration resolved when a run starts
```

### Plugin

代表一个外部系统集成，如 `github`、`gitlab`、`jira`。每个 Plugin 作为独立项目
管理，注册协议、能力、动态配置 schema 和运行时适配器。

### Plugin Registry 与目录发现

企业部署将经过 CI 构建和校验的 Plugin 包安装到受控目录，例如：

```text
/opt/sourcelens/plugins/
  github/1.0.0/
  gitlab/1.0.0/
  jira/1.0.0/
```

平台启动或显式刷新时扫描目录，读取 manifest，并通过 Registry 注册
`plugin_key + version + protocol_version`。目录发现是部署扩展机制，不是授权边界；
Registry 只加载平台允许的内置 handler，不允许 manifest 指定任意 Python import、
shell command、远程组件或前端代码。

Plugin 升级采用新旧版本并存：先安装、校验和启用新版本，再让新执行使用新版本；
运行中的 ExecutionSnapshot 固定 Plugin 版本，旧版本待运行结束后再清理。控制端与
LensNode 在调度/启动时校验 Plugin、版本和协议兼容性。

### SecretMaterial

只保存加密的 Token、App Secret、OAuth refresh token 等秘密材料，并支持版本、轮换、
撤销和状态。它不包含仓库、项目或文件夹范围。

### Connection

代表可以被消费者使用的完整连接：Plugin、endpoint/tenant/audience、非敏感配置、
允许范围、SecretVersion 和授权关系。DataSource、Skill、MCP 绑定 Connection，而不
直接绑定 SecretMaterial。Connection 是当前可编辑配置，不作为历史执行配置的唯一
来源。

### DataSource

DataSource 是 Plugin 的内容摄取消费者，而不是 Connection 的别名。它保存具体资源选择
（如 repository、branch、directory）、索引目标、同步策略、状态和同步历史；Connection
保存可复用认证、endpoint 和平台资源策略。一个 Connection 可被多个 DataSource 复用。

外部 DataSource 的资源选择必须是 Connection 允许范围的子集。`managed_workspace`
不使用外部 Connection，保留现有本地文件、上传和转换生命周期。

### Capability

描述最小业务权限，例如：

- `repository.read`
- `pull_request.read`
- `issue.read`
- `issue.write`
- `jira.issue.search`
- `jira.issue.transition`

Capability 同时用于 UI 展示、绑定校验、运行时授权、风险分级和审计。

V1 只发布只读 capability。平台的资源范围策略和内置 Plugin 代码是实际执行边界；
Provider PAT 的最小权限属于纵深防御，不能以 Connection 的 allowed scope 替代。

### ExecutionSnapshot

Tool 调用或 DataSource 同步实际开始时，控制端将当前有效 Connection 解析成不可变
快照。快照记录 endpoint、规范化资源范围、已授予的 capability、Plugin/manifest
版本、SecretVersion 引用、actor、任务和节点标识；不记录明文 secret。

排队任务在开始时使用当前已批准配置；已经开始的任务只使用自己的快照和短期 lease。
这为实际执行提供可审计、可复现的记录，而不在 V1 引入完整的
ConnectionRevision、绑定迁移和审批图谱。

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

datasource:
  supported: true
  resources: [organization, repository, branch]
  datasource_schema:
    fields:
      - key: repository
        type: provider_resource
        required: true
      - key: branch
        type: string
        required: false
      - key: directory
        type: path
        required: false

tools:
  - key: github_read_file
    capability: repository.read
    side_effect: none
  - key: github_search_code
    capability: repository.read
    side_effect: none
```

Manifest 应包含：

- 身份、版本、展示名称、图标和说明；
- credential/connection 字段类型、默认值、校验和脱敏规则；
- capability、风险等级、读写属性和是否需要确认；V1 只允许只读工具；
- DataSource 资源发现与同步声明；
- DataSource 的资源选择、同步配置和索引输入 schema；
- Tool 名称、描述、输入/输出 JSON Schema 和所需 capability；
- 运行时版本和兼容的 CLI/API 协议版本。

同一个 Manifest 同时声明 Tool Provider 和 Datasource Provider。Plugin 项目可以
独立维护代码、测试、文档和发布流程，SourceLens 主仓库只维护 Registry、通用
Connection、DataSource、Task、Lease 和 schema renderer。

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

禁止提供 `github_raw_exec(command)` 之类的通用命令工具。未来写操作必须有独立
capability、幂等键和按风险配置的用户确认或审批；它不属于 V1 范围。

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
分支、目录、索引目标和同步策略，不能反向修改 Connection 的 endpoint 或资源策略。
`datasource_config` 不得存 Token、endpoint 或 Connection scope；Plugin Datasource
Provider 在创建、更新、资源发现和执行前均验证其资源选择属于 Connection scope。

数据源管理页面分为两层：先选择或创建 Connection，随后按 manifest 的
`datasource_schema` 选择资源并配置同步。API 同样分离 Connection 的 CRUD/验证与
DataSource 的资源选择/调度，避免继续向通用 `config` 字段塞入认证字段。

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
endpoint、tenant、audience 和允许范围。allowed scope 是平台请求约束，不会把 PAT
本身降权；V1 依赖固定的只读 Plugin Tool 和服务端资源校验来限制实际请求。

### 8.2 Secret 交付

V1 的执行位置是 LensNode。默认调用路径：

```text
Control plane → task metadata + connection reference → LensNode
LensNode → node-authenticated lease request → Credential service
LensNode → node-authenticated material exchange → Plugin Runtime
Plugin Runtime → Provider API/CLI
```

任务消息不携带 credential。LensNode 不能直接读取数据库或长期 Token，而是以节点
身份为本次 Run 请求短期 lease。普通 Skill 只获得工具，不获得原始 Token；模型上下文
也不包含 credential 或授权材料。lease 至少绑定 tenant、node、actor、Run、Plugin、
Tool、Capability、资源范围、ExecutionSnapshot 和过期时间，并只在 Plugin Runtime
内存中使用。当前控制面提供三个内部接口：LensNode 先读取
`GET /api/lens/plugin-runtime/snapshots/{snapshot_uuid}/` 获取脱敏的执行配置，
再创建
`POST /api/lens/plugin-runtime/leases/` 获取 opaque lease，再调用
`POST /api/lens/plugin-runtime/leases/{lease_uuid}/material/` 领取快照绑定的短时
材料。第二个响应只对已认证且绑定的 LensNode 返回，材料不写入任务消息、快照、日志，
Provider 使用完成后应立即释放引用。后续可将该接口替换为节点本地密钥代理或
GitHub App installation token，而不改变任务消息契约。

该模型与 Dify 的主要差异是：Dify 常将 credentials 作为 API 到 Plugin Daemon 的
调用数据传递；SourceLens 不将完整 credential 放入任务消息、Tool 参数或普通调用
日志，而由受信任 LensNode 按 ExecutionSnapshot 申请 lease。该模型降低队列消息、
Run 快照和模型上下文泄露凭证的风险，但 LensNode 是受信任执行
边界：若未来支持非平台管理节点，应改为控制端代理调用或更严格的隔离模型。

DataSource 的初始、手动、定时和重试同步都走相同路径：控制端在任务实际开始时解析
DataSource 与 Connection，创建 ExecutionSnapshot；LensNode 只接收 task、snapshot、
datasource 和插件运行参数标识，并以节点身份取得短期 lease。任何 Connection 无效、
资源范围不匹配或 lease 申请失败都应使任务以明确状态失败，不能回退到旧 credential。

### 8.3 强制校验

每次调用必须校验：

1. 当前用户和有效 actor；
2. Assistant/Skill 是否允许使用该 Plugin；
3. Connection 是否属于当前租户且状态有效；
4. Capability 是否满足；
5. endpoint、仓库、项目或文件夹是否在允许范围；
6. 工具读写级别、确认和速率限制；
7. lease、SecretVersion、ExecutionSnapshot 和 Plugin manifest 是否仍有效。

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
ExecutionSnapshot
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
GET  /api/lens/admin/connections/{uuid}/resources/
POST /api/lens/plugin-tools/{provider}/{tool}/invoke/
```

持久化 Run 关联 ExecutionSnapshot；该快照记录 Plugin、Connection、
SecretVersion、Capability 和资源引用，不记录解析后的 secret。

DataSource API 保持数据源生命周期入口，但外部类型的写入契约调整为 `plugin`、
`connection_uuid` 和受 manifest 校验的 `datasource_config`。创建/更新后注册同步策略；
初始、手动、定时和重试任务统一通过 snapshot + lease 下发。迁移期间旧
`source_type`、`config` 和 `credential_uuid` 仅作为兼容读路径，不能成为新写入路径。

## 12. 迁移路径

### Phase 1：Plugin Registry 与 GitHub 只读垂直切片

- 定义独立 Plugin 项目布局、受控目录发现、Registry、受限 manifest、只读 capability、
  Tool/Datasource Provider 和 ExecutionSnapshot 契约；
- 定义 Connection、SecretVersion、节点认证和短期 lease；
- 将现有 GitHub CLI 封装成 Plugin Runtime；
- 实现 `GitHubDatasourceProvider` 并集成 DataSource 管理：Connection 选择、manifest
  驱动的资源配置、资源范围校验和同步任务快照；
- 跑通 Connection → DataSource 初始、手动、定时和重试同步，LensNode 不接收解密
  credential config；
- 跑通 `github_read_file`、`github_search_code` 等只读工具；
- 只支持一种 GitHub 认证方式，并限定允许的 endpoint；
- 完成控制端与 LensNode 的 Plugin/version/protocol 握手；
- 保留旧 DataSourceCredential 读路径，但禁止新功能继续扩展旧模型。

### Phase 2：动态管理页、Skill 迁移与更多 Provider

- 根据 manifest 动态渲染 Connection 与 DataSource 页面；
- 增加资源发现、能力筛选和绑定校验；
- 将现有 GitHub/GitLab/Jira Skills 改为流程 Skill，移除自行读取 Token 和执行
  任意 CLI 的逻辑。
- 增加 GitLab/Jira 内置 Plugin，并分别完成其 DataSource 垂直切片。

### Phase 3：扩展集成与受控能力

- 增加凭证轮换、撤销和 PluginInvocation 审计；
- MCP 通过同一 Connection/Capability 层接入。

写操作、第三方 Plugin、OAuth callback/refresh token rotation 和完整的
ConnectionRevision 仅在明确的产品需求出现后另行设计。

### Phase 4：兼容迁移和清理

- 将旧 DataSourceCredential 映射为 Connection，将旧 DataSource 的可迁移资源字段
  映射为 datasource_config；
- 校验并修正 endpoint/scope，并识别无法自动迁移的 config；
- 提供失败可回滚的双读迁移；
- 删除旧的 DataSourceCredential API 和明文 Reveal 能力。

## 13. 主要风险与取舍

| 风险 | 影响 | 缓解措施 |
|---|---|---|
| LensNode 被攻破后读取运行时凭证 | 高 | 节点身份、短期 lease、内存使用、撤销和受信任节点运营 |
| 动态 schema 过于复杂 | 中 | 第一阶段限制字段类型，保留少量自定义组件 |
| CLI 参数被模型注入 | 高 | 只暴露业务工具，固定参数映射，禁止 raw exec |
| 第三方 API 限流 | 中 | Connection/provider 并发预算、Retry-After、退避 |
| 旧凭证迁移失败 | 高 | 双读、版本化、回滚和迁移前 scope 校验 |
| Tool 与 Datasource 语义混淆 | 中 | 两套 Provider 接口，共享 Connection 但分离执行契约 |
| 数据源仍经消息传递解密 Token | 高 | 同步下发统一改为 task metadata、snapshot 和 lease |
| DataSource 资源越过 Connection scope | 高 | 创建、更新、发现和执行时做子集校验 |
| endpoint 变更导致 Token 外发 | 高 | endpoint allowlist、重新连通性验证、执行快照 |
| Plugin 目录或版本被错误加载 | 高 | 受控安装目录、Registry handler allowlist、制品校验和版本握手 |

## 14. 验收标准

- GitHub Plugin 可以同时出现在 DataSource 和 Skill 工具选择流程中；
- 同一个 Connection 可绑定多个 DataSource 和多个 Skill/MCP；
- 管理页面只依赖 manifest，不写 GitHub/Jira 专用分支；
- 模型只能看到已授权 capability 对应的工具；
- Plugin 内部可并行读取多个 API，且有并发上限、超时、取消和部分失败结果；
- 原始 secret 不进入 prompt、Tool 参数、Run 快照和普通日志；
- V1 只暴露代码圈定的只读 Tool，且不提供 raw exec 或任意 URL 请求；
- LensNode 仅接收任务元数据，并按执行快照取得与任务绑定的短期 lease；
- 外部 DataSource 持有 `plugin + connection + datasource_config`，不持有 Token 或
  endpoint；其资源选择经过 manifest 与 Connection scope 校验；
- 初始、手动、定时和重试同步均不向 LensNode 下发解密 credential config；
- 现有 CLI 能在不改变业务行为的情况下作为 Plugin Runtime 后端执行器。
- Plugin 可作为独立项目构建、测试和发布，并由企业部署安装到受控目录；普通用户
  无 Plugin 上传或安装权限；
- 控制端和 LensNode 拒绝执行未注册、版本不兼容或协议不兼容的 Plugin。

## 15. 待确认问题

1. 第一阶段 Connection 是否只允许管理员创建和授权？
2. GitHub V1 采用 fine-grained PAT 还是 GitHub App？
3. GitHub/GitLab 的资源 scope 是 Connection 级限制，还是允许 DataSource 级细化？
4. Jira 是否同时支持 Cloud OAuth、PAT 和 Server/Data Center Basic Auth？
5. 如何定义 interactive Run、Smart 子助手、定时同步和重试的 effective actor？
6. 外部 DataSource 是否允许在 Connection scope 之下单独配置更窄的资源范围？
7. Plugin Registry 的安装目录、制品校验方式和升级保留窗口如何配置？
