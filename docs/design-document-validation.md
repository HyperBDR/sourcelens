# 设计稿：多格式文档校验（Document Validation）

- 状态：设计讨论中（**未开始开发**）
- 日期：2026-07-28
- 作者：Ray Sun（与 Claude Code 讨论产出）
- 范围：v1 设计。用户上传 PDF/PPT/Word/Excel，让助手对照知识库逐条校验其
  内容是否正确。**明确不做向量库**；依赖 #59（文件上传 + 文档处理地基）。

---

## 1. 需求与目标

用户想上传一份文档（先是 PDF，同类需求含 PPT/Word/Excel），让系统**对照
知识库校验文档中的内容是否正确**——例如"用这份上传的招标书对照我们的参考
标准，逐条核对是否合规"。

目标：把"待校验文档"作为一次 run 的 **subject material**，交给运行在节点端
的 Deep Agent，用 grep 检索知识库（reference）逐条取证，产出**带引用的逐条
裁决报告**。

## 2. 已锁定决策

| 维度 | 结论 |
|---|---|
| 检索方式 | **grep + Deep Agent + ReAct 深度查询**，翻文档原始形态取证。**坚决不上向量库**——SourceLens 的 "source" 即文档原始形态，这是基本原则 |
| 校验实现 | 做成**可插拔 Skill**（`validate-document`），在成熟的 Skill 框架内，**不碰核心引擎** |
| 待校验文档归属 | **一次性 run 内临时产物**，进临时工作区、用完即弃，**永不进 KB 语料**（避免污染检索） |
| subject vs reference | 物理隔离：待校验文档=被告，知识库=事实源，system prompt 显式区分 |
| 处理位置 | **节点端（lensnode）**。源文档、转换器、grep、Deep Agent 四样都在节点；控制端只负责编排 + 文件中转 |
| 文档转换 | **复用 `document_convert.py` 的 converter registry**（markitdown + PyMuPDF + 视觉网关），已支持 pdf/docx/pptx/xlsx |
| 地基依赖 | **#59**（Assistant-side file upload + document processing）提供上传通道、节点转换、union 进 target_dirs、清理 |
| 图像管线 | 扫描/图片 PDF 走同一视觉管线，受 **#149**（超长图缩放坑）影响；#149 修复惠及扫描 PDF 校验 |

## 3. 现状要点（设计建立其上）

- **无向量库/embedding/RAG**：知识库 = DataSource（git/飞书）同步到节点
  工作区的文件 + sidecar，靠 `search_workspace`(ripgrep) + `find_files`(glob)
  检索。**文件系统即索引。**
- **文档转换已存在但仅用于 sync**：`document_convert.py` 的
  `MarkItDownDocumentConverter` 已把 pdf/docx/pptx/xlsx → Markdown，经
  `post_process_documents` 在 datasource sync 时调用。需解耦成单文件可调。
- **用户上传目前仅图片**：`MessageAttachment` = ImageField，走
  `analyze_multimodal_intent` 在**控制端**做视觉预处理、折进问题文本；文档从
  不以文件形式到节点。→ 放开非图上传 = #59。
- **节点↔控制端文件通道已有先例**：
  - 节点→控制端上传：`save_deliverable` → `LensNodeDeliverableUploadView`
    → `RunOutputFile`。
  - 节点←控制端下载：`_download_skill_package`（Bearer token GET、限大小）。
  - 取待校验文件的新接口照抄后者即可。

## 4. 完整处理链路（文本架构图）

```
                     多格式文档校验 · 完整处理链路
          [CP]=控制端(Django)   [NODE]=节点(lensnode)
      标签: (E)已有可复用  (M)需改造  (N)新增

┌─────────────────────────────── 控制端 CP ───────────────────────────────┐
│  ① 用户在会话里上传 PDF/PPT/Word/Excel                                    │
│     POST /api/lens/sessions/{uuid}/attachments/                          │
│     └─ 存控制端临时/附件存储                                              │
│     (M) 现 MessageAttachment=ImageField 纯图锁死 → 放开非图 = #59         │
│     (N) 校验:大小/类型/页数上限;这是"被告",不进 KB                       │
│                            │                                             │
│  ② 建 Run,dispatch_run_to_lensnode() 下发命令 (WebSocket)                │
│     携带: target_dirs=KB(E) · loaded_skills=[validate-document](N)       │
│            · input_file_ref=上传文件 uuid(N)                             │
└────────────────────────────────┬─────────────────────────────────────────┘
                                  │  命令下发
                                  ▼
┌────────────────────────────── 节点 NODE ────────────────────────────────┐
│  ③ 取文件(节点←控制端下载)                                              │
│     GET {control}/lensnode/inputs/{uuid}/  Bearer token, 限大小           │
│     (N) 新接口,照抄 _download_skill_package 先例                         │
│     └─ 落地一次性 run 工作区 /workspace/uploads/<run>/doc.pdf             │
│                            │                                             │
│  ④ 转换: 文档 → Markdown/结构化文本 (document_convert registry)          │
│       • 文字类 PDF/DOCX/PPTX → markitdown → content.md      (E)          │
│       • 扫描/图片 PDF        → PyMuPDF 渲染 + 视觉网关       (E) ⚠#149    │
│       • XLSX/CSV            → 结构化数据 (openpyxl)          (E)          │
│     (M) 现仅 datasource sync 触发 → 解耦成单文件 ad-hoc 可调             │
│                            │                                             │
│  ⑤ 校验(Deep Agent·ReAct,由 validate-document Skill 驱动)  (N)          │
│     ├─ 拆 claim: 从 content.md 抽出可核验声明                            │
│     ├─ 逐条取证: search_workspace(grep) 扫 KB target_dirs   (E)          │
│     ├─ 表格类: analyze_structured_output 确定性数值核对     (E)          │
│     └─ 出裁决: 每条 {claim, 一致/矛盾/无据, 证据: KB路径+行号}           │
│                            │                                             │
│  ⑥ 交付: 校验报告写盘 → save_deliverable(path)             (E)           │
│     POST {control}/api/lens/lensnode/deliverables/                       │
│  ⑦ 清理: 丢弃 /workspace/uploads/<run>/  待校验文档不留痕  (N)           │
└────────────────────────────────┬─────────────────────────────────────────┘
                                  │  产物回传
                                  ▼
┌─────────────────────────────── 控制端 CP ───────────────────────────────┐
│  ⑧ LensNodeDeliverableUploadView → RunOutputFile 挂到 run  (E)           │
│     用户下载校验报告 · 进度沿用 hierarchical progress(#136)  (E)         │
└──────────────────────────────────────────────────────────────────────────┘
```

## 5. 新增/改造清点（真正要写的代码）

| 项 | 类型 | 说明 | 归属 |
|---|---|---|---|
| ① 非图上传通道 | (M) | `MessageAttachment` 放开非图 | **#59** |
| ③ 节点取文件接口 | (N) | 照抄 skill-package 下载,小 | **#59** |
| ④ `document_convert` 解耦单文件调用 | (M) | 从 sync context 拆出,中等 | **#59** |
| ⑦ 一次性工作区清理 | (N) | 用完即弃 | **#59** |
| ⑤ `validate-document` Skill | (N) | **本设计主体**,Skill 框架内 | **本 issue(新建)** |

> ①③④⑦ 属 #59 地基;⑤ 是本需求独有,依赖 #59。②⑥⑧ 全是已有接口接线。

## 6. 待讨论的开放问题

1. **取文件方向**:③ 采"节点主动 GET 控制端"(镜像 skill-package 下载),
   与现有 skill/deliverable 通道一致、节点侧统一管生命周期。备选是控制端
   下发命令时把文件推给节点。倾向"节点拉"。
2. **校验循环形态**:⑤ 用"一次 run 内的 Deep Agent 循环",还是"先转换出
   claim 清单落盘、再逐条起子 agent 校验"?后者对长文档(几百条 claim)
   更可控、可断点续。取决于典型文档规模。
3. **裁决口径**:"矛盾/无据"如何呈现给用户——纯报告,还是可交互逐条下钻到
   证据位置?与 #149 的"失败显性化"哲学一致:检索无证据须标"无据",不臆断。
4. **表格类校验深度**:Excel 校验是数值/结构核对,`analyze_structured_output`
   的确定性算子边界到哪(count/sum/group 够不够,是否需要跨表 join)。

## 7. 与相关 issue 的关系

- **依赖 #59**:上传 + 节点转换 + union target_dirs + 清理(①③④⑦)。
- **受益于 #149**:扫描/图片 PDF 校验共用视觉管线,超长图缩放修复惠及此处。
- **不是 KB 抽象**:延续 #38 决策(KB 层搁置),本设计只在现有 grep 地基上
  加"校验"能力,不新建知识库子系统。
