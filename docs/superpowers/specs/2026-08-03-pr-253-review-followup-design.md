# PR 253 Review Follow-up Design

## Goal

Address the remaining blocking review findings without changing the archive
datasource product scope: failed imports must preserve the last valid target,
accepted uploads must be serialized and registered consistently, and archive
uploads must only target LensNodes that explicitly advertise support.

## Chosen Approaches

### Import commit boundary

Keep the existing extraction and target-swap structure, but retain a reversible
swap transaction until the complete synchronization pipeline succeeds. The
archive adapter returns a private transaction handle after renaming the old
target to a backup and the staged directory to the target. `sync_datasource()`
commits that handle only after marker, manifest, deleted-sidecar cleanup, and
document preprocessing finish. Any exception or cooperative cancellation rolls
the handle back by removing the replacement and restoring the backup.

This is narrower than moving every post-processing step into the staging
directory and directly matches the reviewer's accepted alternative to retain
the backup until the full pipeline succeeds.

### Upload registration and ordering

Serialize create/re-upload registration with a database transaction and a
row-level datasource lock. A file datasource with a pending or running archive
upload returns a conflict before another task is accepted. The transaction
contains datasource metadata updates and `TaskExecution` registration; a
broker enqueue failure rolls both back, while the stored archive is deleted by
the exception path.

The task metadata remains the immutable snapshot for target path and conversion
settings. LensNode dispatch reads those fields from the registered task instead
of re-reading mutable datasource configuration. This prevents an older accepted
archive from running with a newer request's settings.

### LensNode compatibility

New LensNodes advertise `datasource_archive_upload: true` in their existing
hello labels. The API rejects file datasource create and re-upload requests for
nodes without that exact capability, including online older nodes. The frontend
filters file-upload LensNode choices using the same advertised label. No version
comparison or database migration is required.

## Error Behavior

- Marker, manifest, preprocessing, or cancellation failures restore the prior
  target exactly; a failed first import removes its uncommitted target.
- A concurrent archive upload returns HTTP 409 and does not store an archive,
  mutate datasource metadata, or register a task.
- A broker enqueue failure leaves no datasource metadata change or registered
  task and deletes the stored archive.
- A LensNode without the archive capability is rejected by the API even if a
  client bypasses the frontend filter.

## Verification

- LensNode regression tests cover marker failure, manifest failure,
  cancellation after the target rename, successful commit cleanup, and failed
  first-import cleanup.
- Django API tests cover broker failure compensation, concurrent re-upload
  rejection and ordering, immutable task snapshots, and capability rejection.
- Frontend tests cover capability-filtered file-upload LensNode choices.
- Existing focused archive, datasource sync, control-channel cancellation, and
  frontend upload tests remain green, followed by build, lint, migration drift,
  compile, and `git diff --check` verification.
