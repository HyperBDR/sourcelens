# Multi-resource Git DataSources

## Objective

Allow one GitHub or GitLab DataSource to synchronize multiple authorized
repositories/projects. Preserve the current workspace layout and reduce the
production catalog from 48 split GitLab rows to the original 16 logical data
sources.

## Contract

- GitHub datasource config accepts `repositories` (1-50 values).
- GitLab datasource config accepts `projects` (1-50 values).
- Existing singular `repository`/`project` configs remain readable during the
  expand phase.
- Each resource is synchronized below the DataSource target path using a
  deterministic resource-name subdirectory.
- Connection allowlists remain authoritative and are revalidated per resource.

## Migration

- Keep the 5 GitHub and 9 Feishu DataSources unchanged.
- Consolidate GitLab resources into two DataSources: `atomy` (10 projects) and
  `hypermotion` (24 projects), retaining their existing sync policies and
  workspace paths.
- Repoint historical ExecutionSnapshot and PluginInvocation rows to the
  consolidated DataSource while retaining resolved resource and target data.
- Replace old schedules with one schedule per consolidated DataSource.
- Delete the 32 split GitLab DataSource rows only after references are moved in
  one transaction and a production backup is verified.

## Verification

- Provider/unit tests cover singular compatibility, multi-resource validation,
  scope rejection, and deterministic target paths.
- Production audit reports 16 active DataSources, no protected references,
  unique target paths, and complete schedules.
