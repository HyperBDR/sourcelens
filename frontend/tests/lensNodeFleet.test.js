import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = () =>
  readFile(new URL('../src/pages/lens/LensNodes.vue', import.meta.url), 'utf8')

test('LensNode page exposes fleet health and workload', async () => {
  const contents = await source()

  assert.match(contents, /data-testid="lensnode-fleet-summary"/)
  assert.match(contents, /active_run_count/)
  assert.match(contents, /queued_run_count/)
  assert.match(contents, /awaiting_resume_count/)
  assert.match(contents, /last_heartbeat_at/)
})

test('LensNode workload links to filtered run operations', async () => {
  const contents = await source()

  assert.match(contents, /name: 'LensRunObservation'/)
  assert.match(contents, /lensnode: row\.uuid/)
})
