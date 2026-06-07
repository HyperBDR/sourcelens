---
name: workspace-guide-creator
description: Use this skill to create a SourceLens Workspace Guide Skill that explains a selected workspace's repository layout, module ownership, search priority, and recent-change analysis strategy.
---

# Workspace Guide Creator

Create a concise `SKILL.md` for a SourceLens Assistant. The skill should help
Deep Agents understand how to inspect a selected workspace without hard-coded
repository rules in LensNode code.

## Output Requirements

- Generate one complete `SKILL.md`.
- Include YAML frontmatter with `name` and `description`.
- Keep the body concise and operational.
- Describe repository layout, search priority, and stopping rules.
- Prefer exact repository or module matches before broad workspace search.
- For recent-change questions, tell the agent which repositories to inspect
  first and when to summarize.
- Tell the agent to avoid repeatedly querying the same repository with larger
  ranges unless previous evidence is insufficient.
- If a selected workspace is a product-level directory, state that direct child
  repositories should be considered candidate Git repositories.

## Recommended Sections

1. Workspace Overview
2. Repository Map
3. Search Priority
4. Recent Change Workflow
5. Stop Rules
6. Ignore or Low-priority Paths

## SourceLens Binding

Workspace Guide skills are usually bound with:

```json
{"mode": "context", "inject": true}
```

That means the skill is both available to Deep Agents and injected into the
system prompt for every run.
