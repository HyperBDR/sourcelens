# 任务状态命名对照

各项目任务状态命名不一致；本模块与 **Celery result backend** 及 **easy-divine** 对齐，Newshub/Devify 迁移时需做映射。

---

## 本模块（agentcore-task）与 easy-divine

| 常量 | 值 | 含义 |
|------|-----|------|
| PENDING | `"PENDING"` | 已登记，未开始 |
| STARTED | `"STARTED"` | 执行中 |
| SUCCESS | `"SUCCESS"` | 成功结束 |
| FAILURE | `"FAILURE"` | 失败结束 |
| RETRY | `"RETRY"` | Celery 重试中 |
| REVOKED | `"REVOKED"` | 已撤销 |

**与 Celery 一致**：`AsyncResult.status` 即上述字符串（如 `PENDING`, `STARTED`, `SUCCESS`, `FAILURE`, `RETRY`, `REVOKED`）。  
**与 easy-divine task_manager 一致**：枚举与取值完全相同。

---

## 其他项目对比

| 含义 | agentcore / easy-divine | Newshub (articlehub.Task) | Devify (EmailTask) |
|------|-------------------------|---------------------------|--------------------|
| 未开始/已排队 | PENDING | pending | （无；默认 running） |
| 执行中 | STARTED | running | running |
| 成功 | SUCCESS | completed | completed |
| 失败 | FAILURE | failed | failed |
| 撤销/取消 | REVOKED | （无） | cancelled |
| 重试中 | RETRY | （无） | （无） |
| 部分完成 | （无） | partial | （无） |

- **Newshub**：小写（pending, running, completed, failed, partial）；running↔STARTED，completed↔SUCCESS，failed↔FAILURE；多出 partial。  
- **Devify**：小写（running, completed, failed, cancelled）；无 PENDING，cancelled↔REVOKED。

---

## 迁移时映射建议

- **Newshub → 本模块**：pending→PENDING，running→STARTED，completed→SUCCESS，failed→FAILURE；partial 可映射为 FAILURE 或业务存 metadata。  
- **Devify → 本模块**：running→STARTED，completed→SUCCESS，failed→FAILURE，cancelled→REVOKED；创建时若为“刚创建未跑”可写 PENDING。

**结论**：状态机命名已与 **easy-divine** 和 **Celery** 统一；与 Newshub/Devify **未统一**，迁移时按上表做一次映射即可。
