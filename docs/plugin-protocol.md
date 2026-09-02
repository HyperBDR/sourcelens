# SourceLens Plugin Protocol V1

状态：当前实现协议，适用于企业部署的受信任内置 Plugin。

Plugin 是独立项目交付的集成包。它可以同时提供 Connection 管理、Datasource
同步和面向大模型的 Tool，但这些能力都必须通过本协议声明和宿主校验。

## 1. 包结构

宿主只从受控目录发现 Plugin，目录身份必须与 Manifest 一致：

```text
/opt/sourcelens/plugins/<key>/<version>/
  plugin.json
  control.py
  runtime.py
  assets/
```

`key` 使用小写字母开头的短标识，`version` 使用三段式 SemVer。Plugin 项目可以
独立维护源码、测试、文档和发布流程；宿主不从 Manifest 加载任意 Python 模块、
Shell 命令或远程前端代码。

## 2. Manifest 身份与能力族

最小 Manifest：

```json
{
  "key": "github",
  "version": "1.0.0",
  "protocol_version": 1,
  "capability_family": "plugin",
  "handlers": {
    "control": "python_v1",
    "runtime": "python_v1",
    "datasource": "python_v1"
  }
}
```

V1 的 `capability_family` 取值为 `plugin`。它表示 Tool 由受信任的内置 Plugin
Runtime 执行，而不是 MCP Server。实际业务授权仍由 Tool 的 `capability` 字段和
Connection 的资源范围共同决定，例如 `repository.read`。

`mcp` 只表示名称为 `mcp__...` 的 MCP Server Tool；Skill、Plugin 和 MCP 是三个
不同的能力族。为兼容旧模型输出，宿主在路由修复阶段允许将旧的
`required_capabilities=["mcp"]` 映射到当前可用的 `plugin`，但新模型提示词应优先
输出 `plugin`。

为兼容历史 V1 Manifest，工具项缺少 `capability_family` 时继承 Manifest 的值；
未声明时默认为 `plugin`。新发布的 Plugin 必须显式声明该字段。

## 3. Tool 声明

```json
{
  "key": "github_commit_list",
  "description": "List commits in an approved repository.",
  "capability_family": "plugin",
  "capability": "repository.read",
  "side_effect": "none",
  "input_schema": {
    "type": "object",
    "properties": {
      "repository": {"type": "string"},
      "ref": {"type": "string"}
    },
    "required": ["repository"],
    "additionalProperties": false
  }
}
```

宿主必须校验：

- `key` 在同一 Plugin 内唯一，且只能包含小写字母、数字和下划线；
- `description` 是面向模型的完整操作说明，不能包含凭证或隐藏指令；
- `capability_family` 必须是宿主支持的能力族；V1 仅接受 `plugin`；
- `capability` 是稳定的业务权限标识；
- V1 的 `side_effect` 必须为 `none`，只读能力才允许注册；
- `input_schema` 必须是受控的 JSON Schema 子集，不能改变 Connection 资源边界。

## 4. Assistant Guidance

Plugin 可以通过可选的 `assistant_guidance` 提供类似 Skill 的渐进式使用说明：

```json
{
  "assistant_guidance": {
    "summary": "Inspect approved repositories and pull requests.",
    "when_to_use": ["Current repository questions."],
    "topics": [
      {
        "key": "repository",
        "summary": "Read repository metadata and files.",
        "details": "Use an owner/name value from the Connection scope.",
        "tool_keys": ["github_repository_get", "github_read_file"]
      }
    ]
  }
}
```

`summary` 和主题 `summary` 会作为小型索引进入初始上下文；主题的 `details` 不会
默认注入。运行时为存在 guidance 的绑定提供 `plugin_help`，模型可按 Plugin key、
主题或查询词取得受限详情。该工具只查询当前 Run 已绑定的 Plugin，结果上限为
12 KiB。

Registry 必须限制主题数量、文本长度和 `tool_keys`，并确认每个 Tool key 已在同一
Manifest 声明。Guidance 是面向模型的不可信说明，不能覆盖系统规则、Connection
scope、capability 或 Tool schema，也不能包含凭证、隐藏指令、任意 URL 或运行时路径。
Guidance 与 Plugin 版本一同进入执行快照，Plugin 更新后重新加载。

## 5. Runtime 入口

`runtime.py` 必须导出以下固定符号：

```python
PLUGIN_API_VERSION = 1
PLUGIN_KEY = "github"
PLUGIN_VERSION = "1.0.0"

def build_tool(definition, executor):
    """Build one model-facing Tool from a validated declaration."""

def execute_tool(key, client, arguments, secret, endpoint, config):
    """Execute one bounded operation and return JSON-safe data."""

def build_datasource_command(config, output_dir, options):
    """Build one controlled Datasource synchronization command."""
```

宿主会校验入口文件是受控目录中的普通文件，并按 `plugin_key + version + 内容哈希`
缓存加载模块。Tool 注册后必须附带运行时元数据：

```text
metadata.capability_family = "plugin"
metadata.plugin_key = <Manifest.key>
metadata.plugin_version = <Manifest.version>
metadata.capability = <Tool.capability>
```

路由、能力恢复和执行审计只能读取这些显式元数据，不能通过 `github_*`、`jira_*`
等名称前缀猜测能力类型。

## 6. 执行与凭证边界

```text
模型 Tool Call
  → Tool ExecutionSnapshot
  → snapshot-bound Lease
  → 短时 Secret Material
  → Plugin Runtime
  → 受控 Provider API/CLI
  → 清洗后的 Tool Result
```

约束：

- 模型只能看到 Tool 名称、说明和输入 schema；
- Token、Connection 配置中的敏感值和 Lease 内容不能进入模型上下文、Tool 参数、
  普通 Trace Event 或 Tool Result；
- Snapshot 固定 Plugin、Manifest、Connection 配置、资源范围和 SecretVersion；
- Provider 必须再次校验 endpoint、资源范围和参数；
- 外部响应必须做结构校验、大小限制、正文截断和敏感字段过滤；
- Tool 失败返回稳定错误码，不能把第三方原始异常或响应原样交给模型；
- 写操作不属于 V1，未来必须使用新的 capability、幂等键和确认策略。

## 7. Assistant Binding 约定

Direct Assistant 绑定 Plugin 时只提交 Connection 身份和启用状态：

```json
{
  "plugin_bindings": [
    {
      "connection_uuid": "<connection-uuid>",
      "enabled": true
    }
  ]
}
```

Connection 是授权边界，Plugin Manifest 是能力集合来源。绑定生效后，宿主将该
Manifest 声明的全部只读 Tool 注册给模型；前端不展示工具复选框，后端也不信任
客户端传入的工具子集。历史 `tools` 字段可以继续读写以兼容旧数据，但仅作为迁移
信息，不影响运行时全量加载。

同一 Assistant 不能启用多个会产生同名 Tool 的 Connection。通常一个 Plugin Key
只绑定一个 Connection；如果需要不同资源范围，应拆分为不同 Assistant，避免模型
无法区分同名 Tool 的 Connection。MCP Adapter 属于独立兼容入口，仍可显式选择
Manifest 中的 Tool，并与 Direct Plugin binding 共同执行全局 Tool 名冲突校验。

## 8. Datasource 约定

Datasource 与 Tool 共用 Connection，但执行契约分离：Datasource 保存资源选择、
同步策略和目标目录，Plugin 负责资源校验、内容读取和增量同步。资源发现遵循
Manifest 声明的资源依赖；依赖字段变化后才请求对应的 Provider 选项。

Provider 的并发、超时、deadline、取消、Retry-After 和部分失败处理必须通过宿主
提供的 `PluginRequestContext`，禁止自行创建不受限制的线程或请求池。

## 9. 版本与兼容

- `protocol_version` 只代表宿主与 Plugin 的接口版本，不代表业务 capability 版本；
- 同一 `key + version` 在受控目录中只能有一个包；
- 新版本通过新的目录身份并存安装，运行中的 Snapshot 固定旧版本；
- 不兼容的入口、Manifest 或安全语义必须提升 `protocol_version`；
- 新增字段优先采用可选字段和默认值，不能删除既有字段或改变其含义；
- 宿主、Control Runtime、LensNode Runtime 必须拒绝未协商的协议版本。

## 10. 发布前一致性检查

每个独立 Plugin 项目在发布前至少应验证：

1. Manifest 的身份、handler、能力族和 JSON Schema 通过宿主 Registry 校验；
2. 每个声明的 Tool 都能由 `runtime.py` 构造，名称与 schema 完全一致；
3. Tool 的 capability、资源 allowlist、endpoint 校验在 Provider Runtime 中重复执行；
4. 成功、超时、限流、取消、超限和第三方异常均返回稳定错误码；
5. 测试输出、日志、Trace 和错误中不含 Token 或其他认证材料；
6. 同一模型轮次的独立 Tool Call 可以安全并行，不共享可变凭证状态；
7. Plugin 更新后内容哈希不会继续复用旧 Runtime 模块。
