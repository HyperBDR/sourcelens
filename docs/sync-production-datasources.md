# Synchronize Production Datasources

Use `scripts/sync_production_datasources.sh` to convert datasource
configuration from a production `0.48.x` deployment into current Plugin
datasources in the local development database.

The workflow reuses existing local Connections. It never creates
`DataSourceCredential`, `Connection`, `SecretMaterial`, or `SecretVersion`
records and never copies production credential values.

## Conversion

- Feishu folders reuse the current Feishu Connection and become one Plugin
  datasource per production datasource.
- GitHub repositories reuse the current GitHub Connection. Repository values
  are added to its allowlist when missing.
- The retired `HyperBDR/hyperfilelens` GitHub identity is normalized to its
  current `oneprolabs/hyperfilelens` location in datasources and the allowlist.
- GitLab projects reuse the current GitLab Connection. Project values are
  added to its allowlist when missing.
- A legacy Git organization datasource containing multiple repositories is
  split into one Plugin datasource per repository because the current Plugin
  contract permits one repository or project per datasource.
- Split datasource target paths preserve production behavior by appending the
  legacy `target_subdir` to the legacy datasource root.

The production UUID is retained for one-to-one conversions. Split resources
receive deterministic UUIDs derived from the production datasource UUID and
repository identity.

## Run

Preview changes:

```shell
scripts/sync_production_datasources.sh \
  --source-host root@example.com
```

Apply changes:

```shell
scripts/sync_production_datasources.sh \
  --source-host root@example.com \
  --apply
```

When more than one active local Connection exists for a Plugin, select it
explicitly:

```shell
scripts/sync_production_datasources.sh \
  --source-host root@example.com \
  --connection github="Current GitHub" \
  --apply
```

The source API container is detected from the remote `.active_color`. The
default target is `sourcelens-api-dev` and `local-dev-lensnode`. Run the script
with `--help` for all overrides.

## Idempotency and Safety

Datasource matching uses deterministic UUID first, then local LensNode plus
name or target path. Matching Plugin datasources are updated in place. A
resource bound to another Connection or Plugin is a conflict, and the entire
transaction rolls back.

The default is a transactional dry run. The wrapper only accepts target
container names ending in `-dev` and supplies a one-process opt-in environment
variable to the Django command. It does not persist the opt-in.

The SSH snapshot contains datasource configuration and the old credential's
provider and endpoint only. It does not decrypt, transport, log, or store any
production secret. Existing local Connection secrets remain unchanged.

Synchronization history, LensNode runtime state, and Celery Beat tasks are not
copied. Sync policies are retained, but importing does not immediately start
large repository or Feishu synchronization jobs.

Datasource conversion policies retain referenced LLM configuration UUIDs. A
missing local LLM configuration must be created or the policy changed before
document or vision conversion can use that reference.
