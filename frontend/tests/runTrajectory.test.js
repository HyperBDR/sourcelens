import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildTimelineLanes,
  buildTrajectoryRows,
  eventCategory,
  groupTrajectoryRows,
  isSubagentEvent,
  timelineLane
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

test('trajectory rows group by category and step base name', () => {
  const grouped = groupTrajectoryRows(
    buildTrajectoryRows(
      [
        {
          event_id: 'stage-start',
          sequence: 1,
          event_type: 'step.event',
          payload: { name: 'deepagents.runtime.stage.start' }
        },
        {
          event_id: 'stage-done',
          sequence: 2,
          event_type: 'step.event',
          payload: { name: 'deepagents.runtime.stage.done' }
        },
        {
          event_id: 'model-start',
          sequence: 3,
          event_type: 'model.started',
          call_id: 'model-1'
        },
        {
          event_id: 'resource',
          sequence: 4,
          event_type: 'step.event',
          payload: { name: 'resources.materialized' }
        }
      ],
      new Set()
    )
  )

  assert.deepEqual(
    grouped.map((group) => group.label),
    ['deepagents.runtime.stage', 'model', 'resources.materialized']
  )
  assert.equal(grouped[0].rows.length, 2)
  assert.equal(grouped[1].category, 'model')
  assert.equal(grouped[2].rows.length, 1)
})

test('trajectory events expose their filter category', () => {
  assert.equal(eventCategory(events[1]), 'tool')
})

test('timeline lane mapping groups categories into three lanes', () => {
  assert.equal(timelineLane('model'), 'model')
  assert.equal(timelineLane('tool'), 'tools')
  assert.equal(timelineLane('subtool'), 'tools')
  assert.equal(timelineLane('request'), 'input')
  assert.equal(timelineLane('user'), 'input')
})

test('subagent detection reads model is_subagent and task tool name', () => {
  assert.equal(
    isSubagentEvent('model', {
      payload: { is_subagent: true }
    }),
    true
  )
  assert.equal(isSubagentEvent('tool', { payload: { name: 'task' } }), true)
  assert.equal(isSubagentEvent('tool', { payload: { name: 'search' } }), false)
})

test('timeline lanes fill per-call duration and keep events on lanes', () => {
  const span = 10 * 1000
  const summary = {
    first_timestamp: new Date(0).toISOString(),
    last_timestamp: new Date(span).toISOString()
  }
  const timelineEvents = [
    {
      event_id: 'request',
      sequence: 1,
      event_type: 'request.started',
      timestamp: new Date(0).toISOString()
    },
    {
      event_id: 'model-start',
      sequence: 2,
      event_type: 'model.started',
      call_id: 'model-1',
      timestamp: new Date(1000).toISOString(),
      payload: { name: 'agent' }
    },
    {
      event_id: 'model-end',
      sequence: 3,
      event_type: 'model.completed',
      call_id: 'model-1',
      timestamp: new Date(4000).toISOString(),
      payload: { name: 'agent', duration_ms: 3000 }
    },
    {
      event_id: 'tool-start',
      sequence: 4,
      event_type: 'tool.started',
      call_id: 'tool-1',
      parent_call_id: 'model-1',
      timestamp: new Date(5000).toISOString(),
      payload: { name: 'task', arguments: {} }
    },
    {
      event_id: 'tool-end',
      sequence: 5,
      event_type: 'tool.completed',
      call_id: 'tool-1',
      parent_call_id: 'model-1',
      timestamp: new Date(8000).toISOString(),
      payload: { name: 'task', result: 'ok' }
    }
  ]
  const lanes = buildTimelineLanes(timelineEvents, summary)

  assert.deepEqual(
    lanes.map((lane) => lane.key),
    ['input', 'model', 'tools']
  )
  assert.equal(lanes[0].steps.length, 1)
  assert.equal(lanes[0].steps[0].event.event_type, 'request.started')

  const modelStep = lanes[1].steps[0]
  assert.equal(modelStep.event.event_id, 'model-start')
  assert.equal(modelStep.left, 10)
  assert.equal(modelStep.width, 30)
  assert.equal(modelStep.subagent, false)
  assert.equal(modelStep.startMs, 1000)
  assert.equal(modelStep.durationMs, 3000)

  const toolStep = lanes[2].steps[0]
  assert.equal(toolStep.event.event_id, 'tool-start')
  assert.equal(toolStep.left, 50)
  assert.equal(toolStep.width, 30)
  assert.equal(toolStep.subagent, true)
  assert.equal(toolStep.startMs, 5000)
  assert.equal(toolStep.durationMs, 3000)
})

test('timeline lanes treat single events as minimal markers', () => {
  const summary = {
    first_timestamp: new Date(0).toISOString(),
    last_timestamp: new Date(1000).toISOString()
  }
  const lanes = buildTimelineLanes(
    [
      {
        event_id: 'user',
        sequence: 1,
        event_type: 'user.message',
        timestamp: new Date(500).toISOString()
      }
    ],
    summary
  )
  assert.equal(lanes[0].steps.length, 1)
  assert.equal(lanes[0].steps[0].width, 0.6)
})

test('timeline lanes return empty steps without a valid window', () => {
  const lanes = buildTimelineLanes(
    [{ event_id: 'x', event_type: 'model.started', timestamp: null }],
    { first_timestamp: null, last_timestamp: null }
  )
  lanes.forEach((lane) => assert.equal(lane.steps.length, 0))
})
