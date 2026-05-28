# 提交前代码审查（Ray Code Standards）

在每次 `git commit` 前，使用 **ray-code-standards** 对本次变更做审查。

## 审查流程

1. **调用规范**：在 Cursor 中提示「使用 ray-code-standards 对当前变更做提交前审查」，技能路径 `.cursor/skills/ray-code-standards/SKILL.md`。
2. **审查范围**：本次修改/新增文件；命名、结构、风格、与 [AGENTCORE_STRUCTURE_AND_NAMING.md](AGENTCORE_STRUCTURE_AND_NAMING.md) 一致。
3. **自动化**：提交前必须通过 `pytest tests/ -v` 及项目配置的 lint（如 flake8）。

## 提交前清单

- [ ] 已用 ray-code-standards 审查并通过
- [ ] `pytest tests/ -v` 通过
- [ ] Lint 无新增错误
- [ ] 符合 AGENTCORE_STRUCTURE_AND_NAMING
- [ ] 无调试代码、提交信息清晰
