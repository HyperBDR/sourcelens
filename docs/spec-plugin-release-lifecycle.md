# Plugin Release Lifecycle

## Objective

Manage every installed `plugins/<key>/<version>/` package as an immutable
release. Newly discovered versions start in `debugging`; administrators can
publish them and independently assign the `candidate` or `active` deployment
role. Normal Connections, Datasources, Assistants, and new execution snapshots
resolve only the active published release.

## Accepted behavior

- Release state is stored by SourceLens, not inside `plugin.json`.
- `release_status` is `debugging`, `published`, or `retired`.
- `deployment_role` is empty, `candidate`, or `active`.
- A newly discovered filesystem version defaults to `debugging` with no role.
- An existing installation with exactly one version per Plugin is bootstrapped
  as `published` and `active` to preserve current behavior.
- Only a published release can receive a deployment role.
- Each Plugin key has at most one active and one candidate release.
- Publishing freezes a SHA-256 package digest. A changed published package is
  rejected until it is installed under a new version.
- Retiring a release removes its deployment role and prevents new bindings,
  while exact historical snapshot resolution remains available.

## API contract

Administrative endpoints remain under `/api/lens/admin/plugins/`:

- `GET releases/` lists every installed release and its state.
- `POST releases/reconcile/` registers newly installed filesystem versions.
- `POST <key>/releases/<version>/publish/` publishes one debugging release.
- `POST <key>/releases/<version>/role/` accepts
  `{ "deployment_role": "active" | "candidate" | "" }`.
- `POST <key>/releases/<version>/retire/` retires one published release.

All endpoints require an authenticated administrator. Lifecycle failures use a
stable `detail` code and an appropriate HTTP 4xx response.

## Package and runtime layout

```text
plugins/<plugin-key>/<semver>/
  plugin.json
  control.py
  runtime.py
  assets/
```

The control plane chooses the active version for new work. Execution snapshots
continue to store the exact `plugin_version`, and LensNode loads that exact
directory so an active-version switch does not change an in-flight or replayed
execution.

## Testing strategy

- Model tests cover state/role constraints and one-active/one-candidate rules.
- Registry tests cover active selection, debugging exclusion, exact historical
  lookup, and digest mismatch rejection.
- API tests cover reconciliation, publish, role assignment, retirement, and
  administrator authorization.
- Frontend unit tests cover state labels and lifecycle actions.
- Existing Plugin, Connection, Datasource, and LensNode tests must remain green.

## Boundaries

- Always validate directory identity, Manifest identity, SemVer, regular files,
  and package digest before promotion or active resolution.
- Never modify the contents of a published package in place.
- Never expose debugging releases through normal Connection configuration.
- ZIP upload, signature verification, third-party packages, and isolated Plugin
  processes are not introduced by this change.

## Success criteria

- Installing a second version does not change production behavior by itself.
- Administrators can see whether each version is debugging, published, active,
  candidate, or retired.
- Switching active versions is atomic and leaves the previous published version
  installed for rollback.
- New execution snapshots use the selected active version; old snapshots still
  resolve their recorded version.
