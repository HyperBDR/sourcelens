# Lens 模块 — 问答执行流程（含检索内核 / 多轮 / 改写 / 工具层）

> 仓库：**`/root/workspace/sourcelens/`** ｜ 栈：Django + DRF + Celery + Vue3 + LangChain/LangGraph(deepagents) ｜ 日期：2026-06-14
> 范围：从一次用户提问到最终答案的完整链路，覆盖后端调度、查询改写、多轮上下文、LensNode Deep Agent 装配，以及工作区检索（行级命中 / 分页读取 / 正则·glob·输出模式 / 按名找文件）。
> 设计原则：**限制都加在"每次读多少行/命中"上，从不按文件大小排除文件**；历史只带"问答对"不带工具轨迹以防上下文撑爆；任何增强步骤（改写）失败都回退、绝不阻断主流程。
> 关联文档：架构定稿见 [`docs/design.md`](./design.md)。

---

## 一、全链路总览：一次提问的生命周期

```
┌─ 前端 Chat.vue ────────────────────────────────────────────────┐
│  用户在某 session 下提问 (session 绑定一个 Assistant)            │
└───────────────────────────┬───────────────────────────────────┘
                            │ POST 创建 Run
                            ▼
┌─ 后端 Django (lens) ───────────────────────────────────────────┐
│ create_execution_run(): 落库 input_message(user) +              │
│                         output_message(assistant,空占位) + Run   │
│                            │                                    │
│ execute_answer_run() → LangGraph: _lensnode_dispatch(state)     │
│ ┌─────────────────────────────────────────────────────────┐   │
│ │ question = run.input_message.content                     │   │
│ │                                                          │   │
│ │ ┌ RunStep(QUERY_REWRITE, seq=0)  ← 仅当配了 preprocess ┐ │   │
│ │ │  rewrite_query(run):  [#2]                            │ │   │
│ │ │   • 取最近 3 轮 history 作上下文                       │ │   │
│ │ │   • 用 preprocess_model_ref 经 llm.run_completion 改写 │ │   │
│ │ │     → 自包含搜索 query(消解指代/归一术语/纠错别字)     │ │   │
│ │ │   • 失败/没配 → 回退原问题 (绝不阻塞)                  │ │   │
│ │ │  question = 改写结果                                   │ │   │
│ │ └──────────────────────────────────────────────────────┘ │   │
│ │                                                          │   │
│ │ ┌ RunStep(RETRIEVAL, seq=1) ───────────────────────────┐ │   │
│ │ │  validate_run_dispatch (lensnode 在线/审核/任务可用)  │ │   │
│ │ │  create_run_execution_snapshot                        │ │   │
│ │ │    target_dirs = assistant.selected_dirs              │ │   │
│ │ │  build_run_history(run):  [#1]                        │ │   │
│ │ │    session 中本轮之前的 user/assistant 消息            │ │   │
│ │ │    最近 5 轮 / 单条≤2000字 / 合计≤8000字 / 跳过空答     │ │   │
│ │ │  dispatch_run_to_lensnode(run, question) ──WebSocket──┼─┼───┐
│ │ └──────────────────────────────────────────────────────┘ │   │
│ └──────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
                                                                  │
   run_start 命令 { task, question(已改写), history,              │
                    target_dirs, settings, agent_model_ref,       │
                    max_agent_turns(按 agent_rounds 档), agent_rounds }
                                                                  ▼
┌─ LensNode (main.py → executor.py → agent_runtime.py) ──────────┐
│  收到 run_start → LensDeepAgentRuntime._answer_sync             │
│  (装配见 二； 推理见 三)                                        │
│  沿途 emit 事件 ──run_event/llm.response/tool.*──► 后端记录     │
│  ─► 前端 observability 控制台 / SSE 流式答案                    │
└───────────────────────────┬────────────────────────────────────┘
                            ▼
            最终答案：语言强制=提问语言；只基于工作区证据；
            无证据则礼貌告知未找到 (允许桥接笔误/同义后再答)
```

---

## 二、LensNode 内部：Deep Agent 的装配

```
_answer_sync(command):
  ├─ prepare_runtime_resources → skills 文件、mcp.json、私有 scratch 根目录
  ├─ model    = LensGatewayChatModel(agent_model_ref)   → 经 ai-gateway 调 LLM
  ├─ tools    = build_agent_tools(command):
  │     [ search_workspace, read_workspace_file, find_files,        ← 工作区(只读)
  │       summarize_recent_changes, git_log, git_diff ]             ← git 证据
  │     + deepagents 内置: write_file / read_file / ls (私有 scratch 可写)
  │                        write_todos(planning) / task(子agent)
  │     + 已加载的 MCP 工具
  ├─ system_prompt = _system_prompt(scenario, target_dirs, skills):
  │     • scenario 规则(只基于证据 + 桥接笔误/同义 + 拒答常识)
  │     • 只读源 vs 可写 scratch 的区分
  │     • "并行批量调用工具" 指引
  │     • How search/read/find work (见 三/四)
  │     • Required workflow 步骤
  │     • 末尾：FINAL REMINDER 答案语言 = 提问语言
  ├─ backend  = FilesystemBackend(scratch, virtual)  ← read/write/ls 落在 scratch
  ├─ agent    = create_deep_agent(model, tools, prompt, backend, subagents, skills)
  └─ messages = _build_initial_messages(history, question):  [#1]
        [ {user:q1},{assistant:a1}, … 最近若干轮 …, {user: 本轮 question} ]
        → _run_agent_with_turn_limit(agent, messages, max_turns):
             • baseline_ai = 历史里 assistant 条数 (从轮数上限/事件里扣除)
             • agent.stream(...) 逐状态推进；新 AI 轮数 ≥ max_turns → 截断
```

---

## 三、Agent 推理内循环（模型自主决定每一步）

```
            ┌──────── Deep Agent loop (LLM 驱动) ────────┐
question ──►│ 每步可并行批量发多个工具调用              │
            └───────────────────────────────────────────┘
   │
   ├─(A) 定位证据，三选一/组合：
   │     • search_workspace(query, regex?, glob?, output_mode?, …)  [#3]
   │         content → 行级命中 {path,line,text,before,after}
   │         files   → 命中的文件列表
   │         count   → 每文件命中数
   │         (content 无命中 → 回退 files 列表 + note 提示)
   │     • find_files(pattern)  [#4]  → 按名/类型 glob 找文件(mtime 新→旧)
   │     • summarize_recent_changes / git_log / git_diff → 变更类问题
   │
   ├─(B) 读取证据：
   │     • read_workspace_file(path, offset, limit) → 行窗口 + has_more
   │         用 (A) 给的行号当 offset；不够就加大 offset 翻页
   │         目录→PATH_IS_DIRECTORY(递归列候选文件)；二进制→BINARY_FILE
   │     • read_file/ls → 只用于私有 scratch(生成物)，不是工作区
   │
   ├─(C) 需要更多 → 回到 (A)/(B)：换关键词/正则、翻页、按类型过滤
   │
   └─(D) 证据足够 → 综合作答，引用 path
         无任何相关证据 → 礼貌告知未找到 + 建议联系专家
         (语言强制 = 提问语言)
```

---

## 四、`search_workspace` 内部机制（检索的核心）

```
search_workspace(target_dirs, query, *, regex, glob, output_mode,
                 context_lines, case_sensitive, max_results, policy)
  │
  ├─ dirs = 仅保留存在的目录 (root, retrieval_scope)
  │
  ├─ output_mode == "files" → 每目录 _rg_files_with_matches (rg -l) → 去重列表
  ├─ output_mode == "count" → 每目录 _rg_counts (rg -c) → 按 count 降序
  │
  └─ output_mode == "content" (默认):
       terms = [] if regex else _query_terms(query)
              (_query_terms: 词 + 中文 2/3-gram)
       每目录 → _rg_line_matches(...):
         ┌ 构造 ripgrep 命令 ───────────────────────────────────┐
         │ rg --json                                            │
         │   [-i]            ← 除非 case_sensitive               │
         │   [-F]            ← 关键词模式(固定串); regex 模式则去掉 │
         │   -C <context_lines>  -m <每文件命中上限 15>          │
         │   --max-columns 2000 --max-columns-preview  ← 截超长行 │
         │   _rg_glob_args: scope.include_paths(跳过"**/*")      │
         │                + 用户 glob + 排除(目录/扩展名:含 svg/图片)│
         │   -e <pattern…>  ← regex:原样1个; 关键词:每个 term     │
         │   <root>                                             │
         └──────────────────────────────────────────────────────┘
         _run_rg: rg 缺失→None(→Python 逐行兜底,仅关键词模式)
                  返回码>1(如坏正则)→""(当无结果)
         _parse_rg_json → 命中 {path,line,text,before[],after[]}
       │
       ├─ 有命中 → _rank_matches(matches, terms):
       │     按"每文件覆盖的不同 term 数"降序(命中数为次序)
       │     → 最相关文件浮到前面 → 截 max_results
       │     返回 {mode:content, matches, files:[]}
       │
       └─ 无命中 → _iter_scope_files 列出 scope 内文件(有界)
             返回 {mode:content, matches:[], files:[…], note:"换词/正则/find_files"}

  关键闸门 _is_allowed(对搜索候选/读取/列举统一):
    • 必须是文件
    • 路径任意段以 "." 开头 → 排除 (.git/.env/.sourcelens…)
    • 命中 exclude_dirs(.git/.venv/__pycache__/node_modules/dist/build) → 排除
    • 命中 exclude_extensions(.lock/.pyc/.sqlite3 + .svg/png/jpg/字体/.map) → 排除
    • ⚠ 不再有文件大小上限 (max_file_size 已废弃，配了也忽略并打日志)
```

---

## 五、`read_workspace_file` 与 `find_files`

```
read_workspace_file(path, offset=1, limit=250):
  ├─ _resolve_allowed_path: 必须在 target_dirs 之内
  │    不是文件但是目录 → {PATH_IS_DIRECTORY, candidate_files:递归列举}
  │    不在范围 → {PATH_NOT_ALLOWED}
  ├─ _is_binary(嗅探前 4KB 空字节) → {BINARY_FILE}
  └─ read_workspace_window: islice 流式取 [offset, offset+limit) 行
       • 逐行读、读到窗口即停 → 内存由窗口决定，与文件大小无关
       • 单行超 2000 字截断；多读一行判 has_more
       返回 {start_line,end_line,returned_lines,has_more,content(带行号)}

find_files(pattern, max_results=50):     [#4]
  glob_files: 每目录 root.glob(pattern) → 过 _is_allowed
       • 非法 pattern(绝对路径等) → 捕获返回空
       • 上限 GLOB_SCAN_LIMIT=1000 兜底
       • 按 mtime 新→旧排序 → 截 max_results
       返回 {files:[paths]}
```

---

## 六、关键参数与不变量速查

| 环节 | 参数 | 默认 |
|---|---|---|
| 多轮历史 [#1] | 轮数 / 单条 / 合计 | 5 轮 / 2000 字 / 8000 字（只带问答对，不带工具轨迹）|
| 查询改写 [#2] | 触发 / 历史窗口 / 输出上限 | 仅 `preprocess_model_ref` 配置时 / 3 轮 / 400 字 |
| 搜索 [#3] | 总命中 / 单文件命中 / 单行字符 / 上下文 | 50 / 15 / 2000 / ±2 |
| 读取 | 默认窗口 / 最大窗口 | 250 行 / 1000 行 |
| find_files [#4] | 扫描上限 / 排序 | 1000 / mtime 新→旧 |
| 轮数上限 | 按 agent_rounds 档 | flash5 / fast13 / balanced26 / deep50 / max100 |

---

## 七、端到端实例时序图

以真实调试过的 **AGIOne「单价版本怎么部署?」**（"单价"是"单机"的笔误）为例。设为两轮对话：第 1 轮建立历史，第 2 轮是这个笔误追问。文件名 / 行号为实测数据。

```
参与者：
  USER  用户          BE  后端(lens: execution/services)     NODE  LensNode(deep agent)
  LLM   模型网关       WS  工作区(ripgrep / 文件系统)         (DB)  消息/步骤落库 → 前端控制台
═══════════════════════════════════════════════════════════════════════════════════════

━━ 第 1 轮（已发生，构成历史）━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USER ─"AGIOne 有哪些部署方式?"─▶ BE ─▶ NODE … ─▶ 答:"有 All-in-One 单机部署 / 多节点
                                                    host-mode 部署 / 纳管节点部署…"
   (DB) 落库:  msg#1 user="AGIOne 有哪些部署方式?"   msg#2 assistant="…单机部署/多节点…"


━━ 第 2 轮（本次详细追踪）"单价版本怎么部署?"  ← 笔误：单价=单机 ━━━━━━━━━━━━━━━━━━━━━━━

 USER                BE                    NODE                 LLM               WS
  │                   │                     │                   │                 │
  │ "单价版本怎么部署?"│                     │                   │                 │
  ├──────────────────▶│                     │                   │                 │
  │                   │ create_execution_run                    │                 │
  │                   │  msg#3 user / msg#4 assistant(空) / Run  │                 │
  │                   │                     │                   │                 │
  │          ┌────────┤ RunStep(QUERY_REWRITE, seq0)  ★#2       │                 │
  │          │        │ rewrite_query: 取最近3轮历史 + 本轮问题   │                 │
  │          │        ├─ "改写成自包含搜索query。历史:[第1轮Q/A] ─▶│                 │
  │          │        │   本轮:单价版本怎么部署" (preprocess模型) │                 │
  │          │        │◀─ "AGIOne 单机版 部署"  (单价→单机已归一) │                 │
  │          │ (DB) RunStep.detail{original:"单价版本怎么部署",  │                 │
  │          └────────┤   query:"AGIOne 单机版 部署", rewritten:true}                │
  │                   │                     │                   │                 │
  │          ┌────────┤ RunStep(RETRIEVAL, seq1)                │                 │
  │          │        │ validate_dispatch / snapshot(target_dirs=[/workspace/agione])│
  │          │        │ build_run_history → [第1轮Q, 第1轮A]  ★#1│                 │
  │          │        │ run_start{ question:"AGIOne 单机版 部署",│                 │
  │          │        │   history:[…2条…], target_dirs, agent_model_ref,            │
  │          └───────▶│   max_agent_turns:26(balanced) }        │                 │
  │                   │                     │                   │                 │
  │                   │   messages = [q1, a1, "AGIOne 单机版 部署"]  baseline_ai=1 ★#1
  │                   │                     ├─ system_prompt + messages ─────────▶│ (LLM)
  │                   │                     │◀─ 决定: 先搜索 ────│                 │
  │                   │                     │                   │                 │
  │                   │     ★#3 search_workspace("单机部署")  (模型用聚焦关键词)   │
  │                   │                     ├───────────────────────────────────▶│
  │                   │                     │   rg --json -i -F -e 单机 -e 部署 …  │
  │                   │                     │◀── matches(已按相关度排序): ─────────┤
  │                   │                     │   limitations.md:21 "All-in-One 单机部署|
  │                   │                     │      适合演示、测试、PoC…"            │
  │                   │                     │   …install-config-reference.md:78 "### 单机部署"
  │                   │                     │   …:35 "deploy_mode | single | 单机使用 `s…"
  │                   │     ★#4 find_files("**/*install*")  (并行同一步发出)      │
  │                   │                     ├───────────────────────────────────▶│
  │                   │                     │◀── agione-quick-install.md /         │
  │                   │                     │    agione-install-config-reference.md /
  │                   │                     │    agione-multi-node-install.md      │
  │              (DB) │◀ emit tool.search/find.done(事件→控制台)│                 │
  │                   │                     │                   │                 │
  │                   │   read_workspace_file(install-config-reference.md,         │
  │                   │                     │   offset=70, limit=40)  ← 用命中行号 │
  │                   │                     ├───────────────────────────────────▶│
  │                   │                     │◀── 行70-109: "### 单机部署 / 在       │
  │                   │                     │    install.yml 设 deploy_mode: single
  │                   │                     │    / 执行 ./install.sh …"  has_more=… │
  │                   │                     │                   │                 │
  │                   │                     ├─ 证据 + 历史 ─────▶│ (LLM 综合作答)   │
  │                   │                     │◀─ 流式 token ──────┤                 │
  │              ◀━━━━┥◀━ stream(SSE) ──────┤  "你应该是指『单机版/单机部署』。     │
  │  增量显示答案      │  (DB)填 msg#4       │   AGIOne 单机部署：1) install.yml 设  │
  │                   │                     │   deploy_mode: single …(引用          │
  │                   │                     │   agione-install-config-reference.md:78)"
  │                   │ Run=done            │                   │                 │
  ▼                   ▼                     ▼                   ▼                 ▼
```

### 这个例子里各特性如何救场（改造前 vs 现在）

| 关键点 | 改造前的结局 | 现在 |
|---|---|---|
| 笔误"单价" | 文档里"单价"出现 **0 次** → 直接拒答 | **#2 改写** 阶段就把"单价版本"→"单机版部署"；**桥接提示词**再兜底 |
| "版本/它"等指代 | 单条问题、无上下文 | **#1 历史** 让"它/这个版本"能对上第 1 轮提到的 AGIOne |
| 噪音/排序 | 50 条命中被 `.svg`、`部署`等高频词灌满，关键文档沉底 | **#3** 去 svg、按"覆盖关键词数"排序 → install-config-reference 浮顶 |
| 找安装文档 | 只能靠搜内容 | **#4 find_files** `*install*` 直接定位三份安装文档 |
| 读大文件 | 整文件读、可能被旧 256KB 上限吞掉 | **窗口读** offset=70 只取相关 40 行，文件多大都行 |
| 答案质量 | "未找到，请联系专家" | 先点明"你应该是指单机版"，再给 `deploy_mode: single` 步骤并引用文件:行号 |

**一句话**：同一个笔误问题，改造前在"单价字面没命中"就死在第一步；现在它经过 **改写(#2)→带历史(#1)→聚焦搜索+排序去噪(#3)+按名定位(#4)→窗口读** 一条链路，最终给出有引用、可核对的答案。

---

## 附：能力清单与代码落点

| 能力 | 落点 |
|---|---|
| 行级命中 / 分页读取 / 不限文件大小 | `lensnode/lensnode/workspace.py`、`agent_tools.py` |
| #1 多轮上下文（带历史 + 轮数 baseline 扣除） | `backend/lens/services.py: build_run_history`、`lensnode/lensnode/agent_runtime.py: _build_initial_messages / _run_agent_with_turn_limit` |
| #2 QUERY_REWRITE（预处理改写） | `backend/lens/services.py: rewrite_query`、`backend/lens/execution.py`、`backend/lens/llm.py: run_completion`（gated on `Assistant.preprocess_model_ref`）|
| #3 搜索表达力（regex / glob / output_mode / context / case） | `lensnode/lensnode/workspace.py: search_workspace + _rg_*`、`agent_tools.py: search_workspace` |
| #4 按名找文件 | `lensnode/lensnode/workspace.py: glob_files`、`agent_tools.py: find_files` |

> 待办：#5 PDF→Markdown（结论：在接入层 `source_sync` 转一次写 .md 进 workspace，使其可被 grep 检索；运行时按需转换需经 MCP）。
