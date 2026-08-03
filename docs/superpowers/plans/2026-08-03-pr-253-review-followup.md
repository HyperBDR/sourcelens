# PR 253 Review Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the last valid archive datasource on every failed import,
serialize archive registrations, use immutable task configuration, and reject
LensNodes that do not advertise archive support.

**Architecture:** LensNode target replacement becomes a reversible transaction
owned by the complete sync pipeline. Django uses row locks and database
transactions around archive task registration, dispatches file tasks from their
metadata snapshot, and shares an explicit capability contract with the UI.

**Tech Stack:** Python 3, Django, Django REST Framework, Celery, pytest, Vue 3,
Node test runner.

## Global Constraints

- Keep every changed line traceable to PR review 4842698950.
- Do not add a migration for the capability flag; use existing LensNode labels.
- Do not start per-worktree application or container services.
- Use only the canonical shared runtime at `http://localhost:8000` for manual
  verification.

---

### Task 1: Keep Archive Replacement Reversible Through Full Sync

**Files:**
- Modify: `lensnode/lensnode/datasource_archives.py`
- Modify: `lensnode/lensnode/datasource_sync.py`
- Test: `lensnode/tests/test_datasource_archives.py`

**Interfaces:**
- Produces: `ArchiveTargetTransaction(target, backup, cancel_event)` with
  `check_cancelled()`, `commit()`, and `rollback()` methods.
- Produces: private adapter result key `_target_transaction`, consumed and
  removed by `sync_datasource()`.

- [ ] **Step 1: Add failing full-pipeline rollback tests**

  Add tests that first create an owned target, then force
  `write_datasource_marker()` and `write_manifest()` to raise. Each test must
  assert that `old.txt` remains, `new.txt` is absent, and no backup directory
  remains. Add a cancellation test that sets the command cancellation event
  after the target rename and asserts the same rollback. Add a first-import
  marker failure test asserting the uncommitted target is removed.

- [ ] **Step 2: Verify the new tests fail for the reviewed behavior**

  Run:
  `python3 -m pytest -q lensnode/tests/test_datasource_archives.py`

  Expected: marker/manifest/cancellation tests show that the new target remains
  committed or that cancellation is not observed after the rename.

- [ ] **Step 3: Implement the reversible target transaction**

  Change `_replace_target()` to retain the backup and return an
  `ArchiveTargetTransaction`. Attach it to the file adapter result. Wrap all
  marker, manifest, sidecar, and preprocessing work in `sync_datasource()` with
  rollback on `BaseException`, cancellation checks between phases, and commit
  only after all phases succeed.

- [ ] **Step 4: Verify archive and datasource sync tests pass**

  Run:
  `python3 -m pytest -q lensnode/tests/test_datasource_archives.py lensnode/tests/test_datasource_sync.py`

### Task 2: Make Archive Registration Atomic and Ordered

**Files:**
- Modify: `backend/lens/views/datasources.py`
- Modify: `backend/lens/datasource_services.py`
- Test: `backend/lens/tests/test_api.py`
- Test: `backend/lens/tests/test_services.py`

**Interfaces:**
- Produces: `_active_archive_upload_exists(datasource)` using pending and
  running `TaskExecution` states.
- File task dispatch consumes `target_path`, `sync_policy`, and `conversion`
  from the registered task metadata snapshot.

- [ ] **Step 1: Add failing broker and active-upload tests**

  Add API tests proving that a broker exception during re-upload restores
  datasource metadata, leaves no newly registered task, and deletes the stored
  archive. Add a test proving that a pending upload causes the next re-upload
  to return HTTP 409 without storing or registering anything.

- [ ] **Step 2: Add a failing immutable snapshot dispatch test**

  Register a file upload task, mutate the datasource target and conversion
  policy afterward, dispatch it with `_send_lensnode_command` patched, and
  assert the command uses the original literal target and conversion values.

- [ ] **Step 3: Verify the new Django tests fail for current behavior**

  Run:
  `python3 -m pytest -q backend/lens/tests/test_api.py -k DataSourceArchiveUploadTests backend/lens/tests/test_services.py -k datasource`

- [ ] **Step 4: Implement transaction, row lock, and active-upload conflict**

  Wrap upload creation and re-upload metadata/task registration in
  `transaction.atomic()`. Re-fetch re-upload targets with
  `select_for_update()`, reject pending/running archive tasks with HTTP 409,
  and keep archive deletion in the exception compensation path so broker
  failure rolls database state back and removes the file.

- [ ] **Step 5: Dispatch file uploads from their task snapshot**

  Load the `TaskExecution` once in `dispatch_datasource_sync_async()` and use
  its `target_path`, `sync_policy`, and `conversion` metadata for file command
  fields. Continue using live configuration for scheduled Git and Feishu tasks.

- [ ] **Step 6: Verify focused Django tests pass**

  Run the command from Step 3 and confirm zero failures.

### Task 3: Enforce the LensNode Archive Capability

**Files:**
- Modify: `lensnode/lensnode/main.py`
- Modify: `backend/lens/serializers.py`
- Modify: `backend/lens/tests/test_api.py`
- Create: `frontend/src/pages/lens/datasourceCapabilities.js`
- Modify: `frontend/src/pages/lens/DataSourceFormDrawer.vue`
- Modify: `frontend/tests/datasourceArchiveUpload.test.js`

**Interfaces:**
- LensNode hello label: `datasource_archive_upload: true`.
- Produces: `supportsDatasourceArchiveUpload(lensnode)` returning true only for
  the exact advertised boolean capability.

- [ ] **Step 1: Add failing API and frontend capability tests**

  Add an API test that an online approved LensNode without the label cannot
  create a file datasource. Add Node tests that the shared frontend helper
  accepts only an exact true label and that file selection filters unsupported
  nodes while other datasource types retain them.

- [ ] **Step 2: Verify capability tests fail**

  Run the focused Django command from Task 2 and:
  `cd frontend && node --test tests/datasourceArchiveUpload.test.js`

- [ ] **Step 3: Advertise and enforce the capability**

  Add the label to LensNode hello, reject archive-upload serializer requests
  when the selected node lacks it, and use the frontend helper in
  `onlineLensNodes` when the file source type is selected.

- [ ] **Step 4: Verify capability and existing upload tests pass**

  Re-run both commands from Step 2 and confirm zero failures.

### Task 4: Final Verification and Publication

**Files:**
- Verify all files changed by Tasks 1-3.

- [ ] **Step 1: Run focused Python and frontend suites**

  Run LensNode archive/sync/control cancellation tests, Django archive and
  datasource service tests, and frontend archive upload tests.

- [ ] **Step 2: Run static and build checks**

  Run `python3 -m compileall backend lensnode`, Django migration drift check,
  frontend production build, non-fixing ESLint, and `git diff --check`.

- [ ] **Step 3: Synchronize and verify the shared runtime**

  Run the mandatory worktree sync script. If unrelated overlay conflicts remain,
  report that the runtime stayed unchanged and do not copy edits between
  worktrees. Otherwise verify through `http://localhost:8000` only.

- [ ] **Step 4: Commit and push**

  Commit with an English GitHub-facing message, fetch the PR head once more,
  ensure it has not advanced independently, then push the verified local HEAD
  to `zhanghang0915/support-file-upload-data-sources-zip-tar.gz-arch`.
