# Spec: Feishu Datasource Plugin

## Objective

Implement Feishu Drive synchronization as an installed SourceLens datasource
Plugin instead of adding more Feishu-specific control-plane behavior.

The first version serves administrators who configure a Feishu application and
create DataSources that synchronize selected Feishu resource URLs into a
LensNode workspace.

Confirmed scope:

1. The Plugin provides datasource synchronization only. It does not expose
   model-facing Feishu tools.
2. One DataSource accepts multiple mixed Feishu resource URLs. Users do not
   choose a sync mode or classify URLs manually; the Provider recognizes
   folders, documents, sheets, slides, bitables, and wiki nodes when saving.
3. Folder discovery and document resolution use one shared bounded worker
   budget. Discovered and explicit documents are globally deduplicated before
   one bounded export/download phase.
4. The Connection contains only App ID and write-only App Secret. Validation
   proves the credentials can obtain a tenant access token. It does not list or
   persist project/folder scope.
5. Creating or updating a DataSource performs a lightweight read check for
   every configured URL with the selected Connection. Any inaccessible URL
   blocks persistence and is returned in the validation result.
6. Feishu Open Platform is fixed to `https://open.feishu.cn` in V1. Resource
   URLs must use an HTTPS Feishu tenant host.
7. Existing legacy credentials and DataSources remain executable. This
   delivery does not automatically migrate or delete them.

## Tech Stack

- Django and Django REST Framework for Plugin registry, Connection validation,
  and execution snapshots.
- Python Plugin entrypoints under `plugins/feishu/1.0.0/` for the control-plane
  Provider and LensNode datasource command builder.
- Existing LensNode Feishu synchronization adapter for file ingestion and
  post-sync conversion.
- Vue 3 manifest-driven Connection and DataSource forms.
- Django test runner, pytest, and Vitest for regression coverage.

## Commands

```shell
python backend/manage.py test \
  lens.tests.test_feishu_plugin \
  lens.tests.test_plugin_registry \
  lens.tests.test_plugin_snapshots

pytest \
  lensnode/tests/test_feishu_plugin_datasource.py \
  lensnode/tests/test_plugin_runtime.py \
  lensnode/tests/test_datasource_sync.py

cd frontend && node --test tests/pluginIntegrations.test.js
cd frontend && npm run build
git diff --check
```

## Project Structure

```text
plugins/feishu/1.0.0/
  plugin.json       Manifest, Connection schema, and DataSource schema
  control.py        Endpoint, credential, and resource validation
  runtime.py        Snapshot/material validation and sync command construction
  assets/icon.svg   Built-in Plugin icon

backend/lens/
  plugins/          Generic registry and runtime integration
  tests/            Provider, registry, and snapshot tests

lensnode/lensnode/
  datasource_sync.py  Existing bounded Feishu content synchronization adapter

frontend/
  src/pages/lens/   Generic Plugin datasource selection and legacy compatibility
  tests/            Manifest-driven form and edit-flow regression tests
```

## Interface Contract

The Connection owns reusable application authentication:

```json
{
  "plugin_key": "feishu",
  "endpoint": "https://open.feishu.cn",
  "config": {"app_id": "cli_xxx"},
  "allowed_scope": {},
  "secret_value": "<app-secret>"
}
```

The DataSource owns its resource selection and synchronization behavior:

```json
{
  "source_type": "feishu",
  "plugin_key": "feishu",
  "connection_uuid": "<connection-uuid>",
  "datasource_config": {
    "resource_urls": [
      "https://example.feishu.cn/drive/folder/fld_xxx",
      "https://example.feishu.cn/docx/docx_xxx"
    ],
    "resources": [
      {"kind": "folder", "token": "fld_xxx"},
      {"kind": "docx", "token": "docx_xxx"}
    ],
    "recursive": true,
    "max_depth": 10,
    "incremental": true,
    "delete_missing": false
  }
}
```

`resource_urls` is the editable representation. The Provider validates,
canonicalizes, classifies, and deduplicates those URLs when saving, then stores
the derived `resources` beside them for the runtime. App secrets remain only in
`SecretVersion` and short-lived runtime material. Access to an individual
resource is enforced by the Feishu application's own permissions and verified
when the DataSource connection is tested, saved, or synchronized. The
Connection does not store a resource scope or claim to enumerate every
accessible Feishu address.

The Plugin runtime translates the frozen snapshot into the existing bounded
LensNode `feishu` synchronization command. The command is not model-visible and
must validate Plugin identity, endpoint, material, and DataSource config
again before including the in-memory app secret.

## Code Style

Use the repository's existing Python conventions: English docstrings, no
inline comments, three import groups, and a maximum line length of 79.

```python
def validate_datasource_source_type(self, source_type):
    """Bind the Provider to the Feishu datasource adapter."""

    if source_type != "feishu":
        raise DatasourceProviderError(
            "Feishu datasource source type must be feishu"
        )
    return source_type
```

## Testing Strategy

- Provider unit tests validate App ID, fixed endpoint, mixed URL
  classification, duplicate removal, bounded roots, and secret-free errors.
- Registry tests prove a datasource-only Plugin with no tools is discoverable
  and that `feishu` is an allowed datasource source type.
- Snapshot tests prove frozen configuration contains no App Secret and that
  disabled or mismatched Connections fail closed. Feishu resource tokens stay
  available to the runtime only inside validated `{kind, token}` identities;
  credential-shaped token fields elsewhere remain filtered.
- LensNode tests prove snapshot/material validation, command construction,
  cancellation propagation, secret cleanup, and parity with the existing
  folder sync behavior.
- Frontend tests cover one Feishu Plugin option for new DataSources and correct
  editing of both Plugin-backed and legacy Feishu rows.

## Boundaries

- Always: validate third-party responses and resource URLs in the control plane
  and runtime, keep secrets out of snapshots/logs/results, retain bounded
  concurrency and cancellation, and preserve legacy execution.
- Ask first: add model-facing Feishu tools, support Lark international or a
  custom endpoint, auto-migrate production records, or remove the legacy
  credential APIs and runtime.
- Never: place App Secret in DataSource config, accept arbitrary request URLs,
  follow redirects outside the fixed origin, or expose raw Feishu error bodies.

## Success Criteria

1. `feishu` appears as an installed datasource-only Plugin and can create and
   validate a Connection containing App ID and write-only App Secret without a
   project or folder list.
2. A Plugin-backed Feishu DataSource can accept multiple mixed folder and
   document URLs and complete manual or scheduled synchronization through
   ExecutionSnapshot, Lease, and short-lived material.
3. Folder traversal, URL type resolution, global token deduplication,
   export/download, incremental behavior, deletion policy,
   cancellation, progress reporting, manifests, and conversion remain
   behaviorally compatible with the existing folder implementation.
4. A malformed or unsupported resource URL, malformed Feishu response,
   endpoint mismatch, disabled secret, or cancelled task fails with a stable
   safe error.
5. New DataSource creation shows one Feishu path through the Plugin UI. Existing
   legacy Feishu rows remain editable and executable until explicitly migrated.
6. Datasource-only Connections do not appear in Assistant configuration,
   because they expose no model tools.
7. The focused backend, LensNode, frontend, build, and diff checks pass.

## Open Questions

None for this delivery.
