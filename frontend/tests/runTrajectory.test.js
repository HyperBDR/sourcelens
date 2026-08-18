import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildTrajectoryRows,
  eventCategory
} from '../src/admin/pages/lens/runTrajectory.js'

const events = [
  {
    event_id: 'model-start',
    sequence: 1,
    event_type: 'model.started',
    call_id: 'model-1',
    payload: { name: 'agent', messages: [{ content: 'needle' }] }
  },
  {
    event_id: 'tool-start',
    sequence: 2,
    event_type: 'tool.started',
    call_id: 'tool-1',
    parent_call_id: 'model-1',
    payload: { name: 'search', arguments: { query: 'needle' } }
  },
  {
    event_id: 'tool-end',
    sequence: 3,
    event_type: 'tool.completed',
    call_id: 'tool-1',
    parent_call_id: 'model-1',
    payload: { result: 'found' }
  }
]

test('trajectory rows preserve chronological parent depth', () => {
  const rows = buildTrajectoryRows(events, new Set())

  assert.deepEqual(
    rows.map((row) => [row.event.sequence, row.depth]),
    [
      [1, 0],
      [2, 1],
      [3, 1]
    ]
  )
  assert.equal(rows[0].hasChildren, true)
})

test('collapsing a call hides every descendant event', () => {
  const rows = buildTrajectoryRows(events, new Set(['model-1']))

  assert.deepEqual(
    rows.map((row) => row.event.sequence),
    [1]
  )
})

test('trajectory events expose their filter category', () => {
  assert.equal(eventCategory(events[1]), 'tool')
})
