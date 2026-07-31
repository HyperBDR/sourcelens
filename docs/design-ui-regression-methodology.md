# 设计稿：纯前端 UI 回归方法论（UI Regression Methodology）

- 状态：spike 进行中（**最小引擎已落地、可跑；待扩面**）
- 日期：2026-07-28
- 作者：Ray Sun（与 Claude Code 讨论产出）
- 范围：一套**可移植**的纯前端(mock)测试方法论——不测后端逻辑,只做
  UI/UE 基线镜:样式统一、流程统一、翻译完整、提示准确、手机适配、console
  零噪。目标是"引擎通用 + 输入 AI 从代码生成",在任意项目快速复用。

---

## 1. 目标与非目标

**目标**:把人最容易忽略、又最耗精力的东西自动兜住——
- 漏翻(某语言有、另一语言没有;或模板引用了未定义的 key);
- console 警告/报错(Vue 响应式警告、prop 校验、废弃 API、未捕获异常);
- 样式/布局在**空态、错误态、极端载荷**下是否塌;
- **手机视口**下布局是否符合操作习惯、有无溢出/够不着。

**非目标**:不测后端逻辑正确性、不测契约、不测真实鉴权。**一片绿 ≠ 功能对**。
后端正确性交给"真实集成层"(见 §2)。

## 2. E2E 两层分工（本项目已天然分开）

| 层 | 目标 | 载体 | 后端 |
|---|---|---|---|
| **UI/UE 回归层**（本方法论） | 样式/流程/翻译/console/手机适配 | `playwright.ui.config.cjs`（mock、跑构建产物） | 不需要 |
| **真实集成层** | 契约、鉴权、真实数据流 | `playwright.access.config.cjs`（seed 真后端） | 需要 |

两层各司其职、互不膨胀:UI 层冲广度、每 PR 跑;集成层保持薄、只覆盖关键路径。

## 3. 核心思想：引擎通用 + 输入 AI 生成

这是方法论能"覆盖率非常非常全"且可移植的命门。

| 层 | 谁提供 | 内容 | 本 spike 落点 |
|---|---|---|---|
| 路由清册 | **每项目(AI 从代码生成)** | 从 `src/router` 提取页面 | `e2e/ui-regression/routes.js` |
| 默认夹具 | **每项目(AI 从 api-client 生成)** | 各接口 sane 返回 | 同上 `mocks` 字段 |
| i18n 基准 | **每项目(读 locale JSON)** | 键集 | `tests/i18nKeyParity.test.js` |
| Mock 层 + 状态矩阵 | **引擎通用** | 正/逆向状态注入 | `engine/mockApi.js` |
| 断言电池 | **引擎通用** | i18n 泄漏 + console 零噪 | `engine/assertions.js` |
| 遍历循环 | **引擎通用** | 路由×语言×视口×状态 | `engine/harness.js` |

移植到新项目 = 只写"路由清册 + 默认夹具"两样(且可 AI 生成),引擎整包搬。
人只做两件事:**curate 生成结果 + 看报告**。

## 4. 测试矩阵（正向 + 逆向）

```
每个路由 × 语言{en, zh-CN} × 视口{desktop, mobile} × 状态{success, empty, error}
```

- **状态(正/逆向)**:mock 一行钉住后端难复现的空态/错误态,把"数据一空就
  塌""报错文案是英文"跑出来。这是纯前端 mock 相对真后端的**独有优势**。
- **视口**:`desktop 1280×800` / `mobile 390×844`,每页两跑,兜手机适配。
- **语言**:每页双语跑,漏翻当场暴露。

## 5. 断言电池

1. **i18n 双语键集对比**（静态,无浏览器,`tests/i18nKeyParity.test.js`）：
   flatten 两语言 JSON、diff 键集,"en 有 zh 没有 / 反之"直接列出。
   **spike 首跑即抓出 10 个真实漏翻**（`register.google.*` /
   `register.virtualEmail.*` / `register.scene.loadError` 只有中文无英文）。
2. **i18n DOM 泄漏扫描**（`engine/assertions.js` `findI18nLeaks`）：扫渲染后
   DOM,可见的 `some.dotted.key` 即未定义 key 的信号;补静态检查之不足。
3. **console 零噪**（`collectConsoleProblems`）：`page.on('console')` +
   `page.on('pageerror')`,warn/error 即失败,项目可白名单已知良性行。
4. **截图留痕**：每个矩阵格全页截图,既是失败取证,也是 §7 多模态验证的输入。

## 6. 运行

```bash
# 静态 i18n 对比（并入单元层,零依赖）
npm run test:unit

# UI 回归层（自起构建产物 + chromium,纯前端）
npm run test:ui
```

`playwright.ui.config.cjs` 用 `webServer` 自跑 `build && preview`,CI 只需
Node,无后端无 DB。

## 7. 如何验证"流程本身"是对的（核心，非多模态）

**问题**:测试可能"全绿却是错的"——本 spike 就真实发生过:locale 种错 key,
zh-CN 的 18 格全跑在英文下,36 格照样全绿。那怎么确定性地知道流程真被正确
执行了?**不靠人肉看截图,更不靠多模态模型判结果**(用一个不确定、同样会错的
裁判去证明另一个,是循环论证)。唯一可信的路径:

### 7.1 执行证明哨兵（proof-of-exercise）
每根轴锚一个**确定性断言**在"这根轴真生效了"的可判定事实上:
- **语言轴** → 断言该 locale 的哨兵串在页面上(zh-CN 必现 `登录`);没切换 →
  哨兵缺失 → **自动红**。(`routes.js` 的 `sentinels` + `harness.js` 断言)
- **视口轴** → 断言 mobile-only 元素在窄屏可见、宽屏隐藏。
- **状态轴** → 断言空态现空标记、错误态现错误 UI、成功态现数据行。
- **鉴权轴** → 断言落在目标路由而非被弹回 `/login`。

断言只覆盖它检查的维度——所以**每根轴都必须有自己的哨兵**,否则那根轴的
"覆盖"是假的。

### 7.2 负向对照（mutation / 反证）
一个永不会红的测试什么都没验证。**验证测试本身正确的方法 = 故意弄坏、看它
是否如期变红。** 本 spike 已实证:把 locale key 改回错的 → zh-CN 哨兵
`element(s) not found` **确定性变红**;改回 → 回绿。这一步证明断言"有牙齿"。
每加一根轴的哨兵,都配一次负向对照坐实。

### 7.3 双裁判交叉核对（visual-audit CLI，可复用）
多模态既不当唯一裁判(循环),也不弃用,而是当**第二个独立裁判**与确定性断言
**交叉核对**:

- **裁判 A** = 确定性测试结果(pass/fail)。
- **裁判 B** = 可插拔多模态审计:反读最终截图,判"意图是否满足"。
- **一致 → 自动采信;分歧 → 才上人裁定。** 分歧集正是"测试自身在说谎"的
  藏身处(green 却截图违背意图 = locale bug)。

实现为一个**项目无关的 CLI**(`e2e/ui-regression/audit/`):
- `crossCheck.mjs` 编排(确定性)+ `cli.mjs` 入口;
- 视觉后端由 `--judge <module>` **参数注入**,不硬编码——任何项目接自己的
  多模态能力(lensnode 网关 / Claude / …);
- 输入:`{id, intent, screenshot, deterministic}` 清单(intent 可 AI 从
  路由/locale 生成);输出:统一报告,`--gate` 时分歧非零退出。
- **已实证**:对 locale bug 的 before/after 两格,before `det=pass /
  visual=not-satisfied → DISAGREE→human`,after `AGREE`。

**截图**在此定位为裁判 B 的输入 + 人肉抽查/调试辅助;**多模态**是交叉核对的
一方,永不是唯一权威。人只在 A/B 分歧时介入——可扩展。

## 8. 现状与后续

- ✅ 已落可跑并**实跑验证**:
  - 静态 i18n 对比(`npm run test:unit`)**已抓 10 个真实漏翻**。
  - 浏览器层 `npm run test:ui`:3 路由 × 2 语言 × 2 视口 × 3 状态 =
    **36 格全绿(57s)**,并产出 36 张全页截图(Phase 2 的输入)。
- ⏭ 后续:路由清册 3 条 → 全量 34 条(AI 从 `src/router` 生成)、补默认夹具、
  接 Phase 2 多模态验证、评估入 CI。

### spike 暴露的引擎经验（方法论的一部分）

实跑逼出了四个"形态"问题,已在引擎里修正并沉淀为通用规则:

1. **不能用 `networkidle` 等待** —— 本 app 有持久连接(WebSocket/轮询),网络
   永不 idle。改为等 Vue 根节点渲染出内容 + 短 settle。
2. **鉴权按路由 opt-in** —— 统一种 token 会把 `/login` 的"已登录"用户弹走并
   销毁执行上下文。匿名路由不种 token。
3. **拦截必须 hermetic** —— 只拦 `/api/**` 会漏掉外部 CDN/OAuth 资源,在无外网
   沙箱刷 `console.error`。改为拦全部:同源放行、外部 stub 空 200。
4. **区分"注入的失败"与"应用的失败"** —— 逆向 mock 注入 5xx 时,浏览器必然打
   `Failed to load resource`,这是注入的结果非应用缺陷。默认忽略此行,靠
   `pageerror` + 应用级报错抓真问题;error 态才真正测"是否优雅降级"。
6. **测试浏览器的字体必须还原真实用户** —— headless chromium 默认缺 emoji
   字体,导致语言切换器的国旗 emoji(🇺🇸/🇨🇳,`utils/languages.js`)渲染成
   豆腐块 `▯▯`,凭空造出"缺陷"假象。**CI/测试镜像必须钉死字体集**
   (`fonts-noto-color-emoji` + `fonts-noto-cjk`),否则视觉层被环境噪声污染。
5. **绿勾不可信,必须回看截图** —— harness 一开始种错 locale key(种了
   `locale`,app 实际读 `userLanguage`,见 `src/i18n/index.js`),导致 zh-CN
   的 18 格**全跑在英文下**,而 36 格**照样全绿**(断言只查泄漏/console,不查
   语言对不对)。是人肉回看拼图截图发现"zh-CN 那几格还是英文"才揪出来的。
   **教训:断言电池永远只覆盖它检查的维度;可视产物(截图/拼图)是防"测了个
   寂寞"的最后一道关,不可省。** 这也正是 Phase 2 多模态验证要自动化的事。
