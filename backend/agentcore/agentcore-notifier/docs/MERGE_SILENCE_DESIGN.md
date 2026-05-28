# Merge & Silence 设计说明

## 一、核心设计原则

### 合并窗口（Merge Window）

- 聚合同一个 **merge_key** 的告警，在窗口内只发送一次（或合并后发送）。
- **merge_key 必须包含用户维度**，避免不同用户的告警混在一起。

### 静默窗口（Silence Window）

- 在时间窗口内阻止同类告警通知发送。
- 与合并窗口独立配置。
- 可按用户、来源应用、类型等维度生效（规则型静默见下）。

### 通知输出逻辑

- 先按 merge_key 做合并判断，再按静默规则/窗口决定是否发送。
- 静默期内不发送，但告警仍可被计入合并逻辑；静默结束后，按合并结果发送。

---

## 二、merge_key 设计（本模块实现）

```text
merge_key = f"{user_id|'global'}:{source_app}:{source_type}:{source_id}"
```

- **user_id**：保证不同用户告警不混在一起；未传时用 `"global"`，仅与同样无用户的记录合并。
- **source_app / source_type / source_id**：来源应用、类型、ID，保证不同业务/服务/告警分组。

实现位置：`agentcore_notifier.adapters.django.services.merge_and_silence.merge_key()`。

---

## 三、合并与静默的判定（当前实现）

- **合并**：在最近 `merge_window_minutes` 内，若已存在同 merge_key（同 user + source_app + source_type + source_id）、同渠道的**已发送**记录（SUCCESS/FAILED），则本次视为被合并，不再发送。
- **静默**：
  - **时间窗口**：渠道配置 `silence_window_minutes`；在窗口内同 merge_key 的发送会被静默（不发送，记为 SILENCED）。
  - **规则型**：可选配置 `silence_rules`（按 provider_type、source_app、source_type、source_id、user_id 等匹配），匹配则静默。

实现位置：

- 合并/静默窗口判定：`merge_and_silence.should_skip_due_to_merge(..., user_id=...)`
- 规则型静默：`merge_and_silence.should_silence()` / `should_silence_from_rules()`
- 发送任务中先做静默窗口检查，再做合并检查，最后发送：`agentcore_notifier.adapters.django.tasks.send.send_webhook_notification`

---

## 四、时间线示意（按用户维度）

假设合并窗口 10 分钟、静默窗口 20 分钟，merge_key = user + source_app + source_type + source_id：

| 时间 | 用户 | 告警     | 合并组  | 静默     | 行为         |
|------|------|----------|---------|----------|--------------|
| T0   | A    | CPU 高   | A:...   | 生效     | 不发送       |
| T1   | B    | CPU 高   | B:...   | 生效     | 不发送       |
| T5   | A    | CPU 高   | A:...   | 生效     | 不发送       |
| T21  | A    | CPU 高   | A:...   | 结束     | 可发送（与 T0 等是否合并取决于窗口） |
| T22  | B    | CPU 高   | B:...   | 结束     | 可发送       |

每个用户的告警独立合并和静默，互不干扰。

---

## 五、最佳实践（与本实现对应）

1. **merge_key 必须包含用户维度** → 已实现：`merge_key(..., user_id)` 与 `should_skip_due_to_merge(..., user_id)` 均按用户区分。
2. **静默可按用户/服务/类型粒度** → 规则型静默支持 user_id、source_app、source_type、source_id 匹配。
3. **合并窗口 ≤ 静默窗口** → 建议配置时遵守，避免静默结束时过于频繁触发。
4. **调用发送任务时传入 user_id** → 调用方（如 cloud_billing）应传入 `user_id`，以便按用户维度合并与静默。

---

## 六、与“理想模型”的差异说明

设计文档中的 **MergeGroup**（在内存/存储中累积告警，静默结束后一次性发送合并内容）在本模块中**未实现**。当前实现是：

- **合并**：窗口内已有同 merge_key 的**已发送**记录则本次跳过（记为 MERGED），不维护告警列表。
- **静默**：窗口内同 merge_key 已发送则本次跳过（记为 SILENCED），或按规则匹配则静默。

即采用“**同 key 在窗口内只发一次**”的简化模型，而不是“先累积、静默结束后再发一条合并通知”。若需“静默结束后发送合并后的一条通知”，需在业务侧或独立服务中维护 MergeGroup 与定时发送逻辑。
