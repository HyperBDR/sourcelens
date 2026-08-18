# Admin Run Trajectory

## Objective

Provide administrators with a complete, replayable observation view for one
Lens run. The view follows the DeepSeek Harness trajectory vocabulary while
using SourceLens' Django, Vue, and LensNode architecture.

The trajectory must preserve the request envelope, conversation and reasoning
events, model timing and usage, nested tool calls, retries, interruption,
compaction, and terminal state. Checkpoints remain execution-recovery state;
they are not the trajectory store.

## Tech Stack

- Django and Django REST Framework
- PostgreSQL or SQLite through the Django ORM
- Vue 3, JavaScript, and Tailwind CSS
- LensNode Python runtime and LangGraph SQLite checkpoints

## Commands

```shell
pytest backend/lens/tests
pytest lensnode/tests
cd frontend && npm run test:unit
cd frontend && npm run build
```

Browser acceptance uses `ego-browser`, not Playwright.

## Project Structure

- `backend/lens/models.py`: append-only trace event model
- `backend/lens/run_trace.py`: validation and idempotent ingestion
- `backend/lens/views/admin_runs.py`: administrator read API
- `backend/lens/consumers.py`: authenticated LensNode WebSocket ingestion
- `lensnode/lensnode/agent_runtime/`: event production and call hierarchy
- `lensnode/lensnode/checkpoint.py`: trace continuation metadata
- `frontend/src/admin/pages/lens/RunObservation.vue`: trajectory workbench

## Event Contract

Every event has a stable `event_id`, contiguous run-local `sequence`,
`event_type`, source timestamp, attempt number, and JSON payload. Optional
correlation fields are `checkpoint_id`, `turn`, `step`, `call_id`, and
`parent_call_id`.

The initial vocabulary is grouped as follows:

- Request: `request.started`, `request.completed`, `system.snapshot`, and
  `tools.snapshot`
- Conversation: `user.message`, `context.message`, `assistant.message`, and
  `assistant.reasoning`
- Model: `model.started`, `model.first_token`, `model.completed`, and
  `model.failed`
- Tools: `tool.started`, `tool.completed`, `tool.failed`, and
  `subtool.*`
- Control: `turn.*`, `step.*`, `retry.*`, `checkpoint.saved`,
  `checkpoint.restored`, `compaction.*`, `cancelled`, `interrupted`, and
  `run.completed`

Unknown event types are retained so the contract can evolve without losing
evidence. Required envelope fields and JSON value shapes are validated at the
ingestion boundary.

## Data Model

`RunTraceEvent` is an append-only row owned by one `Run`:

- UUID primary key
- stable event ID and contiguous run-local sequence
- attempt, event type, and source timestamp
- optional checkpoint, turn, step, call, and parent-call identifiers
- complete JSON payload and server creation timestamp

`(run, event_id)` and `(run, sequence)` are unique. Indexes support ordered
run reads and call-tree lookup. At-least-once delivery is safe because an
identical event is accepted idempotently; conflicting reuse is rejected.

Existing `RunStep.detail` remains unchanged for current status rendering and
compatibility inside the current release. It is not the source of truth for
new trajectory reads.

## API

LensNode sends bounded event batches for its assigned run over the authenticated
control WebSocket. The server
validates run ownership, envelope shape, contiguous ordering, uniqueness, and
payload shape, then appends the batch transactionally.

The administrator run detail endpoint exposes a paginated trajectory ordered
by sequence. Filters include event type, free-text payload search, call ID,
and sequence cursor. The response includes event counts, first and last source
timestamps, and aggregate model/tool timing where available.

## UI Behavior

The Run Observation page adds a trajectory workbench with:

- compact time overview and category counts
- text search and category filters
- chronological Turn / Step / Request ledger
- collapsible nested tool and subtool calls
- event summary rows for role, status, duration, usage, and TTFT
- a detail inspector showing full prompt, schema, arguments, result, error,
  metadata, and raw JSON

The existing status summary stays available. The new ledger reads only the
trajectory API and represents a single run.

## Checkpoint Contract

Checkpoint metadata schema version 2 adds:

- `trace_schema_version`
- `last_trace_seq`
- `current_attempt`
- `open_call_ids`
- `open_span_ids`
- `parent_call_map`

The metadata only lets a resumed runtime continue sequence allocation and
close or reconnect open calls. Completed run trajectory rows are never deleted
with checkpoints. Older checkpoints do not need compatibility and fail closed
when their schema is unsupported.

## Testing Strategy

- Model tests cover uniqueness, indexes, ordering, and cascade behavior.
- Service tests start failing first and cover append, idempotent replay,
  conflicting duplicates, invalid envelopes, ordering, and transactionality.
- API tests cover LensNode authorization, administrator permission, filters,
  cursor pagination, and aggregate metadata.
- LensNode tests cover event sequencing, nested calls, retry/resume continuity,
  open-call checkpoint state, and terminal events.
- Frontend tests cover projection, grouping, category mapping, and collapse.
- Build and targeted regression suites run before browser acceptance.

## Boundaries

- No migration or rendering compatibility for historical runs or old
  checkpoints.
- No trajectory redaction in this iteration.
- Administrator permission checks remain mandatory.
- External event envelopes remain strictly validated.
- No session-level aggregation across runs.
- DSH source is a behavioral reference; React/Cordis implementation code is
  not copied.

## Success Criteria

1. A new run records every supported event as immutable ordered rows.
2. Delivery retries cannot duplicate events or silently overwrite conflicts.
3. Resume continues event ordering and call relationships from checkpoint
   metadata.
4. An administrator can search and inspect complete model, tool, reasoning,
   retry, compaction, cancellation, and interruption evidence for one run.
5. Non-administrators cannot read trajectory data or append events for runs
   they do not own as a LensNode.
6. Targeted backend and LensNode tests, frontend tests and build, and
   `ego-browser` acceptance pass.

## Delivery Slices

1. Persist and ingest append-only trajectory events.
2. Read and summarize trajectory events through the administrator API.
3. Emit complete LensNode events and persist resume cursors in checkpoints.
4. Project events into the administrator trajectory workbench.
5. Run regression, browser acceptance, and multi-axis review.
