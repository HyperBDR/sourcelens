# 设计稿：公开可分享问答（Public Shareable Q&A）

- 状态：设计已定稿（**未开始开发**）
- 日期：2026-06-21
- 作者：Ray Sun（与 Claude Code 讨论产出）
- 范围：仅 v1 设计；不含 SEO/SSR、整段会话分享、来源展示（见「不在本期范围」）

---

## 1. 需求与目标

用户在 SourceLens 里与助手（Assistant）产生的「问答」可以被**显式分享**为公开内容：

- **单条问答分享页**：一个问题 + 它的回答，只读、免登录、可凭链接访问。
- **公开问答列表页**：已分享并经审核的问答，按助手聚合成可浏览列表，免登录访问。

核心动作：用户从自己的私有问答里选择「分享」→ 生成一份**公开快照** → 立即获得独立链接；经管理员审核后进入该助手的公开列表。

## 2. 已锁定决策

| 维度 | 结论 |
|---|---|
| 分享粒度 | **单条问答 = 一个 `Run`**（不做整段会话）|
| 列表范围 | **按助手聚合**：`/lens/assistants/:slug/qa` |
| 单条页 | `/lens/qa/:token`，凭不可猜 token，免登录，**展示查看数** |
| 发布模型 | **两级**：单条链接自助；进公开列表需**管理员审核** |
| 公开内容 | 仅「问题 + 回答正文」快照，**剥离来源/检索过程**，**作者匿名** |
| 存储 | 新增 `SharedQA` **快照**模型 |
| 列表分页 | 「加载更多」按钮（offset/cursor），不做无限滚动 |
| SEO | **v1 不做**（纯 SPA，字段/URL 预留）|
| 权限 | 公开读全开放；分享需登录 + 归属校验；审核 `IsAdminUser` |

## 3. 现状要点（设计建立其上）

- 一条问答的数据形态：`Session` → `Message`(user/assistant) → `Run`（`input_message` 绑 `output_message`）。
- `Session/Run/Message` 当前均私有（`IsAuthenticated` + 按 `user` 过滤）。
- 已有匿名公开端点 `GET /lens/public/assistants/<slug>/`（`authentication_classes=[] / permission_classes=[]`）。
- 分享基址 `public_base_url` 存于 `GlobalSetting`（即「分享地址」）。
- 前端纯 SPA（Vue 3 + Tailwind），无 SSR/SEO。

## 4. 数据模型（新增 `SharedQA`，快照式）

```
SharedQA
  uuid
  token            # secrets.token_urlsafe，不可猜，公开 URL 用，唯一索引
  run_id           # FK→Run, on_delete=SET_NULL, 仅做溯源
  assistant_id     # FK→Assistant, 列表聚合用
  assistant_name   # 助手名快照（助手改名/删除不影响已分享页）
  question         # 文本快照，来自 input_message.content
  answer           # 文本快照，来自 output_message.content
  title            # 默认取问题前 N 字，可编辑
  is_listed        # bool，是否进公开列表（由管理员控制）
  status           # PUBLISHED / HIDDEN
  published_by_id  # FK→User，仅内部，不对外暴露
  view_count       # int，单条页展示
  published_at / created_at / updated_at

索引: unique(token); (assistant_id, is_listed, status, -published_at)
```

**为什么快照**：① 公开内容不可变；② 与私有会话生命周期解耦（用户删会话/会话被改，分享页不受影响、也不会 404）；③ 不直接暴露私有模型。

## 5. 状态机

```
私有问答 (Run, status=DONE)
  └─[用户点“分享”]──→ SharedQA{status:PUBLISHED, is_listed:false}
        │                         → /lens/qa/<token> 立即可访问（免登录）
        ├─[管理员审核通过]──→ is_listed:true   → 进 /lens/assistants/<slug>/qa 列表
        ├─[管理员下架]──────→ status:HIDDEN    → 链接与列表均返回 404/Gone
        └─[用户取消分享]────→ 删除 SharedQA    → 链接失效
```

## 6. API

### 匿名（`authentication_classes=[] / permission_classes=[]`，沿用 PublicAssistantView 模式）
- `GET /lens/public/qa/<token>/` — 单条。仅要求 `status=PUBLISHED`（不要求 is_listed）。返回 `{title, question, answer, assistant_name, assistant_slug, view_count, published_at}`。命中即 `view_count += 1`（可异步/节流）。
- `GET /lens/public/assistants/<slug>/qa/?limit=&offset=` — 列表。仅 `PUBLISHED & is_listed=true`，按 `-published_at`，分页。返回 `{results:[{token,title,answer_snippet,view_count,published_at}], next_offset}`。

### 登录用户（`IsAuthenticated` + 校验 `run.session.user == request.user`）
- `POST /lens/runs/<uuid>/share/` `{title?}` — 建快照（`is_listed=false`），返回 `{token, url}`。若已分享则返回既有记录（幂等）。
- `GET /lens/shares/` — 我分享过的列表。
- `DELETE /lens/shares/<uuid>/` — 取消分享（删除记录）。

### 管理员（`IsAdminUser`）
- `GET /lens/admin/shares/?listed=&status=` — 全量/按状态筛选（审核队列）。
- `PATCH /lens/admin/shares/<uuid>/` `{is_listed?, status?}` — 通过上榜 / 撤下列表 / 下架 / 恢复。

### 风控
- 匿名端点限流 + 单条/列表响应可缓存。
- `POST share` 防刷（按用户限流）。

## 7. 页面规划

### 7.0 复用与新建
- **复用**：`MarkdownRenderer`、`BaseButton`、`BaseModal`、`BaseLoading`、`StatusBadge`、`useToast`、`copyToClipboard`、lucide 图标。
- **提取共享工具**：`publicBaseUrl()` 从 `Assistants.vue` 提到 `utils/lens.js`。
- **新建组件**：`PublicLensHeader.vue`、`QaShareModal.vue`、`SharedQaCard.vue`。
- 设计令牌：`border-line` `bg-surface/-sunken` `text-ink-{400..900}` `rounded-lg/xl` `shadow-soft*` `primary/brand`；无暗色模式。

### 7.1 聊天内「分享」入口 + 弹窗（改 `Chat.vue` + 新 `QaShareModal`）
- 按钮：助手消息下方 `.message-actions` 行追加第 3 个 `icon-btn`（`Share2`，30×30）。
- 显示条件：仅登录用户、`Run.status=DONE`、属于本人；匿名访客不显示。
- 弹窗：警示语（公开泄露风险）+ 可编辑标题（默认取问题前 N 字）+ 问答预览 + 主按钮「创建链接」。**点击后才** `POST .../share/`（避免误公开）。成功后显示只读链接 + 复制按钮 + 「进入公开列表需管理员审核」提示；已分享态显示链接 + 「取消分享」（二次确认）。
- 反馈：`useToast` 成功/失败；已分享的消息分享按钮高亮。

### 7.2 单条问答页 `/lens/qa/:token`（新 `pages/lens/PublicQa.vue`，allowAnonymous）
- 外壳：`PublicLensHeader`（logo + 「向 {助手} 提问 →」+ 登录）。
- 正文：居中阅读栏 `max-w-3xl`：助手 chip（→列表页）→ 问题卡（`bg-surface-sunken`，`text-ink-900` 加粗）→ `MarkdownRenderer` 渲染回答 → 元信息（发布时间 + 查看数，**无作者**）+ 复制链接 → 底部转化 CTA（去和助手对话）。
- 状态：加载 `BaseLoading`；不存在/已取消/已下架 → 友好空页（沿用 assistantNotFound 风格）。
- 客户端设 `document.title`（仅标签，不做 OG/SSR）。

### 7.3 公开列表页 `/lens/assistants/:slug/qa`（新 `pages/lens/PublicQaList.vue`，allowAnonymous）
- 外壳：`PublicLensHeader`。
- 正文：页头（助手名 + 「公开问答(N)」+ 去提问）→ `SharedQaCard` 列表（问题标题 1–2 行截断 + 回答片段 2 行 + 发布时间 + 查看数；整卡点击进单条页）→ 底部「加载更多」（ghost 按钮，分页）。
- `SharedQaCard`：`rounded-lg border border-line bg-surface px-4 py-3 hover:bg-surface-sunken cursor-pointer`。
- 仅展示 `PUBLISHED & is_listed=true`。
- 状态：空「该助手暂无公开问答」；加载 `BaseLoading`；加载更多按钮 loading 态。

### 7.4 我的分享 `/lens/my/shares`（新 `pages/lens/MyShares.vue`，requiresAuth）
- 入口：Chat 侧栏**用户 dock 菜单**「我的分享」。
- 表格（Assistants.vue 表格约定 + `StatusBadge`）：标题 | 助手 | 状态（`仅链接`/`已上榜`/`已下架`）| 发布时间 | 操作（复制链接 / 取消分享，二次确认）。
- 状态：空「你还没有分享任何问答」；加载常规。v1 只读 + 取消，不做批量。

### 7.5 管理台审核 `/management/lens/shares`（新 `pages/management/LensShares.vue`，admin）
- 表格（admin 约定 + `StatusBadge`）：标题 | 助手 | 状态/是否上榜 | 发布人 | 发布时间 | 查看数 | 操作。
- 筛选 tab：`待审核`(PUBLISHED & is_listed=false) / `已上榜` / `已下架`。
- 行操作：预览 / 通过上榜（is_listed=true）/ 撤下列表 / 下架（status=HIDDEN）/ 恢复。

## 8. 路由新增

| 路径 | 组件 | meta |
|---|---|---|
| `/lens/qa/:token` | `pages/lens/PublicQa.vue` | `allowAnonymous` |
| `/lens/assistants/:slug/qa` | `pages/lens/PublicQaList.vue` | `allowAnonymous` |
| `/lens/my/shares` | `pages/lens/MyShares.vue` | `requiresAuth` |
| `/management/lens/shares` | `pages/management/LensShares.vue` | `requiresAuth` + admin |

## 9. 入口/导航

- 助手回答 → 分享按钮 → `QaShareModal`（建链接/复制/取消）。
- 聊天页头 →「查看公开问答」→ 列表页。
- 列表卡片 → 单条页；单条页助手 chip → 列表页；单条/列表 CTA → 助手聊天。
- 用户 dock 菜单 → 我的分享；管理台 lens → 问答审核。

## 10. i18n

新增 `lens.qa.*`（en + zh-CN 同步），分组：`shareModal.*` / `single.*` / `list.*` / `mine.*` / `admin.*`；复用现有 `lens.share.copied/copyFailed`。

## 11. 风险与对策

1. **内容泄露（最重）**：回答源自私有数据源 → 仅快照问答正文、剥离来源；发布弹窗明确警示；两级审核 + 下架兜底。
2. **删除语义**：删私有会话不影响已分享快照；用户可主动取消。
3. **作者隐私**：不暴露 user 身份。
4. **滥用**：匿名端点限流 + 缓存；`share` 按用户限流。
5. **SEO 预留**：URL/字段不阻碍未来加预渲染。

## 12. 不在本期范围

- SEO / SSR / 预渲染（公开页对爬虫不可见）。
- 整段会话（多轮）分享。
- 来源/引用展示（默认剥离；后续可作独立开关）。

## 13. 工作量分解（开发时参考）

- **后端**：`SharedQA` 模型 + migration、序列化器、三组端点（public/user/admin）、权限、限流。（小–中）
- **前端**：2 个匿名页 + 聊天分享弹窗 + 我的分享 + 管理台审核；3 个新组件；`publicBaseUrl()` 提取。（中）
- **i18n**：`lens.qa.*` 中英。
- **不含**：SEO/SSR。
