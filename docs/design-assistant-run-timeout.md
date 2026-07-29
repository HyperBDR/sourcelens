# Assistant Run Timeout

## Objective

Make the Assistant analysis level the single source of truth for a Run's
wall-clock limit. `LENSNODE_REQUEST_TIMEOUT_S` remains a transport request
timeout and no longer limits the complete Agent Run.

## Contract

The control plane resolves `agent_rounds` to a duration and snapshots it on
`RunExecution`:

| Analysis level | Run timeout |
|---|---:|
| `flash` | 300 seconds |
| `fast` | 600 seconds |
| `balanced` | 900 seconds |
| `deep` | 1800 seconds |
| `max` | 3600 seconds |

`run_start` carries the immutable snapshot as `run_timeout_s`. LensNode uses
that value for the complete Run deadline. For compatibility with an older
control plane, LensNode derives the same duration from `agent_rounds` when
`run_timeout_s` is absent. It never falls back to
`LENSNODE_REQUEST_TIMEOUT_S` for the Run deadline.

The existing environment variable continues to control LensNode HTTP
transport operations, including AI Gateway calls, deliverable uploads, and
Skill package downloads. Renaming that transport setting is outside this
change.

## Commands

```shell
docker exec sourcelens-api-dev python manage.py test lens.tests.test_services
docker exec sourcelens-api-dev python manage.py makemigrations --check
cd lensnode && .venv/bin/python -m pytest tests/test_executor.py tests/test_config.py
pytest
```

## Project Structure

- `backend/lens/models.py` stores the immutable execution snapshot.
- `backend/lens/services.py` resolves the Assistant level and builds
  `run_start`.
- `backend/lens/migrations/` evolves the database schema.
- `lensnode/lensnode/executor.py` enforces the received Run deadline.
- `backend/lens/tests/` and `lensnode/tests/` cover the contract.

## Code Style

```python
RUN_TIMEOUT_SECONDS_BY_ROUNDS = {
    "flash": 300,
    "fast": 600,
}
```

Keep mappings explicit, validate protocol input at the LensNode boundary, and
use English comments and docstrings with a 79-character line limit.

## Testing Strategy

- Backend unit tests verify every level mapping and the execution snapshot.
- Backend service tests verify `run_start.run_timeout_s` uses the snapshot.
- LensNode unit tests verify the command value wins over the environment
  transport timeout and that the level fallback is compatible.
- Migration checks and existing backend/LensNode suites guard regressions.

## Boundaries

- Always: snapshot the resolved duration and keep existing Runs immutable.
- Always: retain an eventual hard wall-clock deadline for runaway execution.
- Never: use `LENSNODE_REQUEST_TIMEOUT_S` as the Run wall-clock fallback.
- Never: let later Assistant edits change an in-flight Run.
- Out of scope: transport timeout renaming, retry policy, and timeout UI error
  copy.

## Success Criteria

- A `max` Assistant receives a 3600-second Run deadline even when
  `LENSNODE_REQUEST_TIMEOUT_S=240`.
- All five analysis levels resolve deterministically.
- New LensNode works with `run_start` payloads from both new and old control
  planes.
- Existing transport requests continue using `LENSNODE_REQUEST_TIMEOUT_S`.
- Relevant backend and LensNode tests pass.
