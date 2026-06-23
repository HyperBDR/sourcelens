# 设计稿：助手访问控制（Assistant Access Control）

- 状态：设计已定稿（**未开始开发**）
- 日期：2026-06-23
- 作者：Ray Sun（与 Claude Code 讨论产出）
- 范围：仅 v1 设计；助手两档可见性 + 组/用户授权 + QA 继承。**明确不做多租户**（业务确认为单组织内部 + 对外公开分享）。

---

## 1. 需求与目标

当前任何登录用户都能在切换器里看到**全部**助手，匿名用户凭 slug 链接也能打开任意助手。需要为助手引入访问控制：

- **公开（public）**：匿名可见、可凭链接访问、可分享，与现状一致。
- **私有（private）**：必须**登录且被授权**才能看到 / 访问；未授权者在切换器里看不到，匿名打开其链接被拒。
- **QA 列表/分享继承所属助手的可见性**：私有助手的公开问答画廊与单条分享链接，对未授权者一律不可见。

## 2. 已锁定决策

| 维度 | 结论 |
|---|---|
| 隔离层级 | **不做多租户**；单组织 + 公开分享，组足够 |
| 可见性 | 助手两档：`public` / `private` |
| 授权主体 | **组为主 + 用户为辅**，落成独立 `AssistantAccess` 授权表 |
| 不复用 | **不挂到 `accounts.Role`**（那是 `visible_features` 功能可见性轴，与数据访问正交）|
| QA | **继承所属助手**可见性 |
| 管理入口 | 管理员在管理控制台（助手编辑抽屉）设可见性 + 勾授权组/用户 |
| 恒可见 | 超管 / 管理员看全部，便于管理私有助手与授权 |
| 存量数据 | 迁移为 `public`（零行为变化、零风险）|
| 新建默认 | 建议 `private`（安全默认），admin 就绪后再切 public（**唯一待你点头的小项**）|
| 演进预留 | 授权表预留 `level` / `granted_by` / `expires_at`，P2 加访问级别/到期/申请审批/审计，**不改结构** |

## 3. 现状要点（设计建立其上）

- `Assistant` 无 owner、无可见性字段，仅 `status`(active/disabled)。
- 三条暴露路径：
  - `AssistantViewSet.list`（`IsAuthenticated`）：**任何登录用户看到全部助手**；工作区切换器（`Chat.vue` → `listAssistants()`）与管理台（`Assistants.vue`）共用此端点。
  - `PublicAssistantView` `GET /lens/public/assistants/<slug>/`（匿名）：返回某 active 助手元数据。
  - `PublicSharedQAListView` / `PublicSharedQAView`（匿名）：按 slug/token 看助手的公开问答。
- **无匿名"列全部助手"端点**——匿名访问永远是按 slug 单点。
- 提问链路 `Session`/`Run`（`IsAuthenticated`）：匿名只能看公开助手元数据与公开 QA，真正提问需登录。
- 已有成员原语：Django `auth.Group`（管理台 Groups 页）；`accounts.Role` 已能绑 user / group，但只管 `visible_features`。
- 组/用户列表接口已存在：`GET /v1/management/groups/`、`GET /v1/management/users/`。

## 4. 数据模型

```
Assistant（新增 1 字段）
  visibility   # choices: public | private；default=private（新建）；存量迁移→public

AssistantAccess（新增授权表）
  uuid
  assistant_id   # FK→Assistant, on_delete=CASCADE, related_name="access_grants"
  group_id       # FK→auth.Group, null=True, on_delete=CASCADE
  user_id        # FK→User, null=True, on_delete=CASCADE
  level          # CharField, default="view"（预留；P2: ask / manage）
  granted_by_id  # FK→User, null=True, on_delete=SET_NULL（审计）
  created_at

约束: Check(group 与 user 恰有一个非空); unique(assistant, group); unique(assistant, user)
索引: (assistant_id); (group_id); (user_id)
```

**为什么用独立授权表而非两个 M2M 字段**：演进路线上会长出"访问级别 / 到期 / 申请审批 / 审计"，这些都是给授权关系**加列/加状态**——独立 through 表一次到位，避免日后从裸 M2M 迁移。一张表也便于统一查询"该助手授权给了谁"和统一渲染 UI。

## 5. 判定规则（单一事实来源）

```
assistant.is_accessible_by(user):
  if assistant.visibility == public:        return True            # 含匿名
  if user 未登录:                            return False
  if user is admin (见 §8 定义):             return True
  if AssistantAccess(assistant, user=user).exists():        return True
  if AssistantAccess(assistant, group∈user.groups).exists(): return True
  return False
```

- 提供管理器方法 `Assistant.objects.visible_to(user)` 给列表过滤，`assistant.is_accessible_by(user)` 给单点校验，二者同源，杜绝列表能过滤但入口可绕过的不一致。
- 匿名 = `user=AnonymousUser`，只能命中第一条（public）。

## 6. API 改动

### 助手列表/详情（`AssistantViewSet`，`IsAuthenticated`）
- `list` / `retrieve` 的 queryset 改为 `Assistant.objects.visible_to(request.user)`。
- **管理员旁路**：管理台需看全量以管理私有助手；管理员（§8）不被过滤。非管理员只得到「public ∪ 被授权」。

### 匿名公开端点（沿用 `authentication_classes=[]`）
- `PublicAssistantView`：`visibility != public` → **404**（不泄露存在性）。
- `PublicSharedQAListView` / `PublicSharedQAView`：先解析所属 assistant，`visibility != public` → **404**（QA 继承）。

### 提问/会话入口（防绕过，**关键**）
- `SessionViewSet.create` / `RunViewSet.create`：创建前校验 `assistant.is_accessible_by(request.user)`，否则 **403**。光过滤列表不够——否则登录用户可凭 uuid/slug 直接对私有助手发起会话。

### 授权管理（管理员，`IsAdminUser`）
- 授权随助手 `PATCH /lens/assistants/<uuid>/` 一起提交：`{ visibility, access_grants:[{group_uuid?|user_uuid?}, ...] }`，序列化器内 diff 同步 `AssistantAccess`（参考现有 `skill_bindings`/`mcp_bindings` 的写法）。
- 读：`AssistantSerializer` 增 `visibility` + `access_grants`（含 group/user 的 uuid+name 快照，供 UI 回显）。

## 7. 前端/页面规划

### 7.0 复用与新建
- **复用**：`BaseDrawer`、`FormRow`、`BaseButton`、`StatusBadge`、`useToast`；组/用户多选可用现成 `GET /v1/management/groups|users/`。
- **新建组件**：`AssistantAccessEditor.vue`（可见性 toggle + 私有时的组/用户多选授权列表）。

### 7.1 管理台 — 助手编辑抽屉（改 `AssistantFormDrawer.vue`）
- 新增「可见性」段：`公开 / 私有` 单选（或 toggle）。
- 选「私有」时展开 `AssistantAccessEditor`：两个多选（授权组 / 授权用户），已授权项以可删 chip 列出；空态提示「私有助手默认仅管理员可见，请添加授权组或用户」。
- 列表页（`Assistants.vue`）增一列或 chip 显示 `公开/私有`（复用 Skills 页 Type 列的徽标风格）。

### 7.2 工作区 — 聊天切换器（`Chat.vue`）
- 无需改逻辑：`listAssistants()` 后端已过滤，切换器自然只列可访问助手。
- 私有助手公开聊天页（匿名 / 未授权登录用户）：`getPublicAssistant` 返回 404 → 复用 `assistantNotFound` 友好空页；未登录访客额外给「登录后可能可访问」CTA。

### 7.3 公开问答页（`PublicQa.vue` / `PublicQaList.vue`）
- 私有助手 → 后端 404 → 复用现有「不存在/已下架」空页，不区分"私有"与"不存在"（避免存在性泄露）。

## 8. 「管理员」的定义（需对齐）

- 管理 API（授权读写）用现有 `IsAdminUser`（Django `is_staff`）。
- 助手列表「看全量」旁路：建议同样以 `is_staff` 为准；若 `admin_console` 功能持有者未必 `is_staff`，需确认二者是否对齐，或为列表旁路引入显式权限（如 `lens.view_all_assistants`）。**此为唯一需要敲定的鉴权细节。**

## 9. 迁移注意点

- 加 `Assistant.visibility`（default 设计上为 `private`，但**数据迁移把所有存量助手置为 `public`**，保持现网行为不变）。
- 新建 `AssistantAccess` 表 + 约束/索引。
- 无需回填授权（存量皆 public）。
- worker/scheduler 不涉及；纯 API 路径改动，api-dev 重启执行迁移即可。

## 10. i18n

- `lensAdmin.*`：`fields.visibility`、`visibility.public/private`、`access.*`（授权组/用户、空态、提示）。
- 公开页复用现有 not-found 文案；如需「请登录查看」CTA，加 `lens.access.loginToView` 等少量键。中英同步。

## 11. 风险与对策

1. **绕过列表直连**（最重）：必须在 `Session/Run create` 校验访问权（§6），与 list 过滤同源（§5）。
2. **存在性泄露**：私有一律 404，不区分"私有/不存在"。
3. **QA token 外泄**：私有助手的 token 链接同样 404（继承）。
4. **缓存**：公开 QA 若加缓存，必须按 `visibility` 区分，私有绝不进缓存。
5. **性能**：`visible_to` 用 `EXISTS` 子查询 + 索引；列表对 grants 做 prefetch。
6. **admin 定义不一致**（§8）：上线前对齐 `is_staff` 与 `admin_console`。

## 12. 不在本期范围（P2，授权表已预留）

- 访问级别（view / ask / manage）。
- 授权到期（`expires_at`）与自动收回。
- 「申请访问 → 管理员审批」工作流（一条 pending 授权记录）。
- 授权审计视图（谁在何时授给谁）。
- 多租户（明确不做）。

## 13. 工作量分解（开发时参考）

- **后端**：`visibility` 字段 + `AssistantAccess` 模型 + migration（存量→public）；`visible_to`/`is_accessible_by`；`AssistantViewSet` 过滤 + 管理员旁路；`Public*` 三端点继承拦截；`Session/Run create` 校验；`AssistantSerializer` 读写 grants；测试（公开/私有 × 匿名/未授权/已授权/管理员 + 绕过用例）。（中）
- **前端**：`AssistantFormDrawer` 可见性段 + `AssistantAccessEditor`；`Assistants.vue` 可见性列；私有空页文案。（中）
- **i18n**：`lensAdmin` 可见性/授权键 + 少量公开页文案，中英。
- **不含**：访问级别 / 到期 / 申请审批 / 审计 / 多租户。
