import assert from 'node:assert/strict'
import test from 'node:test'

import {
  activitiesForNode,
  applyRuntimeEvent,
  calculateRunElapsedSeconds,
  createRuntimeState,
  getMessageTimestamp,
  inferProgressLocale,
  normalizePlanSteps,
  normalizeStages,
  scrollConversationToBottomAfterRender,
  selectLiveProgressText,
  selectStructuredProgress,
  summarizeStageProgress,
  summarizePlanProgress
} from '../src/pages/lens/runtimeEvents.js'

test('waits for the conversation to render before scrolling to the bottom', async () => {
  let container = null

  const scrolled = await scrollConversationToBottomAfterRender(
    () => container,
    async () => {
      container = { scrollTop: 0, scrollHeight: 640 }
    }
  )

  assert.equal(scrolled, true)
  assert.equal(container.scrollTop, 640)
})

test('does nothing when the conversation container is not rendered', async () => {
  const scrolled = await scrollConversationToBottomAfterRender(
    () => null,
    async () => {}
  )

  assert.equal(scrolled, false)
})

test('uses run completion time for assistant messages', () => {
  const createdAt = '2026-07-27T05:00:00.000Z'
  const completedAt = '2026-07-27T05:03:12.000Z'

  assert.equal(
    getMessageTimestamp({
      role: 'assistant',
      created_at: createdAt,
      completed_at: completedAt
    }),
    completedAt
  )
  assert.equal(
    getMessageTimestamp({
      role: 'user',
      created_at: createdAt,
      completed_at: completedAt
    }),
    createdAt
  )
})

test('uses the progress node language for nested activity labels', () => {
  assert.equal(inferProgressLocale('执行并分析所需操作'), 'zh-CN')
  assert.equal(inferProgressLocale('Execute required operations'), 'en')
})

test('restores active run elapsed time from its server creation time', () => {
  assert.equal(
    calculateRunElapsedSeconds(
      { created_at: '2026-07-27T05:00:00.000Z' },
      Date.parse('2026-07-27T05:01:42.900Z')
    ),
    102
  )
})

test('caps elapsed time at the server finish time', () => {
  assert.equal(
    calculateRunElapsedSeconds(
      {
        created_at: '2026-07-27T05:00:00.000Z',
        finished_at: '2026-07-27T05:00:30.000Z'
      },
      Date.parse('2026-07-27T05:10:00.000Z')
    ),
    30
  )
})

test('returns zero for missing, invalid or future run timestamps', () => {
  const now = Date.parse('2026-07-27T05:00:00.000Z')

  assert.equal(calculateRunElapsedSeconds({}, now), 0)
  assert.equal(calculateRunElapsedSeconds({ created_at: 'invalid' }, now), 0)
  assert.equal(
    calculateRunElapsedSeconds({ created_at: '2026-07-27T05:00:01.000Z' }, now),
    0
  )
})

test('reduces route, phase, plan and capability events', () => {
  let state = createRuntimeState()
  state = applyRuntimeEvent(state, {
    event_type: 'route.selected',
    visibility: 'user',
    payload: {
      route: 'plan_execute',
      complexity: 'complex',
      evidence_requirement: 'none'
    }
  })
  state = applyRuntimeEvent(state, {
    event_type: 'phase.changed',
    visibility: 'user',
    payload: { phase: 'executing' }
  })
  state = applyRuntimeEvent(state, {
    event_type: 'plan.updated',
    visibility: 'user',
    payload: {
      steps: [
        { id: 'one', title: 'Inspect code', status: 'completed' },
        { id: 'two', title: 'Implement change', status: 'in_progress' }
      ]
    }
  })
  state = applyRuntimeEvent(state, {
    event_type: 'capability.blocked',
    visibility: 'user',
    payload: {
      capability: 'skill',
      reason: 'configuration',
      recovery: 'Ask an administrator to configure the Skill.'
    }
  })

  assert.equal(state.route, 'plan_execute')
  assert.equal(state.complexity, 'complex')
  assert.equal(state.evidenceRequirement, 'none')
  assert.equal(state.phase, 'executing')
  assert.equal(state.plan[1].status, 'in_progress')
  assert.equal(state.capabilityBlock.capability, 'skill')
})

test('keeps execution failures separate from capability availability', () => {
  let state = createRuntimeState()
  state = applyRuntimeEvent(state, {
    event_type: 'execution.failed',
    visibility: 'user',
    payload: {
      reason: 'execution_failed',
      capability: 'skill',
      error_type: 'transient'
    }
  })

  assert.equal(state.capabilityBlock, null)
  assert.equal(state.executionFailure.reason, 'execution_failed')
  assert.equal(state.executionFailure.error_type, 'transient')
})

test('restores the correct block card from terminal run details', () => {
  const capabilityState = applyRuntimeEvent(createRuntimeState(), {
    type: 'done',
    outcome: 'blocked',
    termination_detail: {
      reason: 'capability_unavailable',
      error_type: 'capability'
    }
  })
  const executionState = applyRuntimeEvent(createRuntimeState(), {
    type: 'done',
    outcome: 'blocked',
    termination_detail: {
      reason: 'execution_failed',
      error_type: 'transient'
    }
  })

  assert.equal(capabilityState.capabilityBlock.error_type, 'capability')
  assert.equal(capabilityState.executionFailure, null)
  assert.equal(executionState.capabilityBlock, null)
  assert.equal(executionState.executionFailure.error_type, 'transient')
})

test('ignores internal events and applies terminal outcome', () => {
  const initial = createRuntimeState()
  const unchanged = applyRuntimeEvent(initial, {
    event_type: 'plan.updated',
    visibility: 'internal',
    payload: { steps: [{ title: 'secret' }] }
  })
  const terminal = applyRuntimeEvent(unchanged, {
    type: 'done',
    outcome: 'partial',
    termination_detail: { reason: 'capability_unavailable' }
  })

  assert.deepEqual(unchanged.plan, [])
  assert.equal(terminal.outcome, 'partial')
  assert.equal(terminal.terminationDetail.reason, 'capability_unavailable')
})

test('summarizes plan progress for a compact answer header', () => {
  assert.deepEqual(
    summarizePlanProgress([
      { id: 'one', title: 'Inspect', status: 'completed' },
      { id: 'two', title: 'Implement', status: 'in_progress' },
      { id: 'three', title: 'Verify', status: 'pending' }
    ]),
    {
      completed: 1,
      total: 3,
      currentTitle: 'Implement',
      isComplete: false,
      isTerminal: false
    }
  )
  assert.equal(summarizePlanProgress([]), null)
})

test('marks incomplete plan progress as terminal after the run ends', () => {
  assert.deepEqual(
    summarizePlanProgress(
      [
        { id: 'one', title: 'Inspect', status: 'completed' },
        { id: 'two', title: 'Implement', status: 'in_progress' },
        { id: 'three', title: 'Verify', status: 'pending' }
      ],
      { terminal: true }
    ),
    {
      completed: 1,
      total: 3,
      currentTitle: 'Implement',
      isComplete: false,
      isTerminal: true
    }
  )
})

test('shows real plan completion before lower-level execution details', () => {
  assert.equal(
    selectLiveProgressText({
      planProgressText: 'Completed 1/3 · Implement change',
      latestStep: 'Reading files',
      phaseText: 'Executing',
      activityMessage: 'Loading resources',
      fallbackText: 'Running'
    }),
    'Completed 1/3 · Implement change'
  )
})

test('shows real direct-execution stages before raw tool details', () => {
  assert.equal(
    selectLiveProgressText({
      stageProgressText: 'Completed 1/3 · Execute required operations',
      latestStep: 'Reading files',
      phaseText: 'Executing',
      activityMessage: 'Calling a tool',
      fallbackText: 'Running'
    }),
    'Completed 1/3 · Execute required operations'
  )
})

test('uses plans before stages and stages before generic fallback', () => {
  const stages = [{ id: 'execute', title: 'Execute', status: 'in_progress' }]
  const plan = [{ id: 'step-1', title: 'Inspect', status: 'in_progress' }]

  assert.deepEqual(selectStructuredProgress({ plan, stages }), {
    kind: 'plan',
    items: plan
  })
  assert.deepEqual(selectStructuredProgress({ plan: [], stages }), {
    kind: 'stage',
    items: stages
  })
  assert.deepEqual(selectStructuredProgress({ plan: [], stages: [] }), {
    kind: null,
    items: []
  })
})

test('keeps raw tool activity out of the primary progress text', () => {
  assert.equal(
    selectLiveProgressText({
      planProgressText: '',
      latestStep: 'Loading context...',
      phaseText: 'Understanding the request',
      activityMessage: 'Calling a tool',
      fallbackText: 'Running'
    }),
    'Understanding the request'
  )
})

test('falls back through phase, activity and run status', () => {
  assert.equal(
    selectLiveProgressText({
      phaseText: 'Analyzing',
      activityMessage: 'Loading resources',
      fallbackText: 'Running'
    }),
    'Analyzing'
  )
  assert.equal(
    selectLiveProgressText({
      activityMessage: 'Loading resources',
      fallbackText: 'Running'
    }),
    'Loading resources'
  )
  assert.equal(selectLiveProgressText({ fallbackText: 'Waiting' }), 'Waiting')
})

test('ignores stale plan revisions after reconnect', () => {
  let state = createRuntimeState()
  state = applyRuntimeEvent(state, {
    event_type: 'plan.updated',
    visibility: 'user',
    payload: {
      revision: 2,
      steps: [{ id: 'new', title: 'New plan', status: 'in_progress' }]
    }
  })
  state = applyRuntimeEvent(state, {
    event_type: 'plan.updated',
    visibility: 'user',
    payload: {
      revision: 1,
      steps: [{ id: 'old', title: 'Old plan', status: 'pending' }]
    }
  })

  assert.equal(state.planRevision, 2)
  assert.equal(state.plan[0].title, 'New plan')
})

test('reduces ordered direct-execution stages and ignores stale revisions', () => {
  let state = createRuntimeState()
  state = applyRuntimeEvent(state, {
    event_type: 'stage.updated',
    visibility: 'user',
    payload: {
      id: 'execute',
      title: 'Execute required operations',
      status: 'in_progress',
      summary: 'Started 1 operation',
      order: 2,
      revision: 2
    }
  })
  state = applyRuntimeEvent(state, {
    event_type: 'stage.updated',
    visibility: 'user',
    payload: {
      id: 'understand',
      title: 'Understand the request',
      status: 'completed',
      order: 1,
      revision: 3
    }
  })
  state = applyRuntimeEvent(state, {
    event_type: 'stage.updated',
    visibility: 'user',
    payload: {
      id: 'execute',
      title: 'Stale title',
      status: 'pending',
      order: 2,
      revision: 1
    }
  })

  assert.equal(state.stageRevision, 3)
  assert.deepEqual(
    state.stages.map((stage) => stage.id),
    ['understand', 'execute']
  )
  assert.equal(state.stages[1].status, 'in_progress')
  assert.equal(state.stages[1].summary, 'Started 1 operation')
})

test('attaches readable activity to the current progress node', () => {
  let state = createRuntimeState()
  state = applyRuntimeEvent(state, {
    event_type: 'stage.updated',
    visibility: 'user',
    payload: {
      id: 'execute',
      title: 'Execute required operations',
      status: 'in_progress',
      order: 2,
      revision: 1
    }
  })
  state = applyRuntimeEvent(state, {
    agent_event: 'tool.read_file.invoke',
    activity: 'running_tool'
  })
  state = applyRuntimeEvent(state, {
    agent_event: 'tool.read_file.invoke',
    activity: 'running_tool'
  })
  state = applyRuntimeEvent(state, {
    agent_event: 'tool.read_file.done',
    activity: 'completed'
  })
  state = applyRuntimeEvent(state, {
    agent_event: 'tool.run_skill_artifact.start',
    activity: 'running_tool'
  })

  assert.deepEqual(activitiesForNode(state, 'execute'), [
    {
      id: 1,
      nodeId: 'execute',
      kind: 'readingContext',
      count: 2
    },
    {
      id: 2,
      nodeId: 'execute',
      kind: 'queryingData',
      count: 1
    }
  ])
})

test('keeps only the latest twenty progress activities', () => {
  let state = createRuntimeState()
  state = applyRuntimeEvent(state, {
    event_type: 'stage.updated',
    visibility: 'user',
    payload: {
      id: 'execute',
      title: 'Execute required operations',
      status: 'in_progress',
      order: 2,
      revision: 1
    }
  })
  for (let index = 0; index < 22; index += 1) {
    state = applyRuntimeEvent(state, {
      agent_event:
        index % 2 === 0
          ? 'tool.read_file.invoke'
          : 'tool.run_skill_artifact.start',
      activity: 'running_tool'
    })
  }

  assert.equal(activitiesForNode(state, 'execute').length, 20)
  assert.equal(activitiesForNode(state, 'execute')[0].id, 3)
})

test('moves subsequent activity to the newly active plan node', () => {
  let state = createRuntimeState()
  state = applyRuntimeEvent(state, {
    event_type: 'plan.updated',
    visibility: 'user',
    payload: {
      revision: 1,
      steps: [
        { id: 'one', title: 'Inspect', status: 'in_progress' },
        { id: 'two', title: 'Verify', status: 'pending' }
      ]
    }
  })
  state = applyRuntimeEvent(state, {
    agent_event: 'tool.search_workspace.invoke',
    activity: 'running_tool'
  })
  state = applyRuntimeEvent(state, {
    event_type: 'plan.updated',
    visibility: 'user',
    payload: {
      revision: 2,
      steps: [
        { id: 'one', title: 'Inspect', status: 'completed' },
        { id: 'two', title: 'Verify', status: 'in_progress' }
      ]
    }
  })
  state = applyRuntimeEvent(state, {
    agent_event: 'tool.analyze_structured_output.start',
    activity: 'running_tool'
  })

  assert.equal(activitiesForNode(state, 'one')[0].kind, 'searchingSources')
  assert.equal(activitiesForNode(state, 'two')[0].kind, 'analyzingResults')
})

test('normalizes stage bounds and drops invalid stages', () => {
  const stages = normalizeStages([
    {
      id: 'x'.repeat(100),
      title: 'T'.repeat(300),
      summary: 'S'.repeat(300),
      status: 'failed',
      order: 99
    },
    { id: 'invalid', title: 'Invalid', status: 'unknown' }
  ])

  assert.equal(stages.length, 1)
  assert.equal(stages[0].id.length, 64)
  assert.equal(stages[0].title.length, 240)
  assert.equal(stages[0].summary.length, 240)
  assert.equal(stages[0].order, 12)
})

test('summarizes real stage completion for a compact answer header', () => {
  assert.deepEqual(
    summarizeStageProgress([
      { id: 'one', title: 'Understand', status: 'completed', order: 1 },
      { id: 'two', title: 'Execute', status: 'in_progress', order: 2 },
      { id: 'three', title: 'Finish', status: 'pending', order: 3 }
    ]),
    {
      completed: 1,
      total: 3,
      currentTitle: 'Execute',
      currentSummary: '',
      isComplete: false,
      isTerminal: false
    }
  )
})

test('deduplicates replayed artifact events', () => {
  const event = {
    event_type: 'artifact.created',
    visibility: 'user',
    payload: {
      filename: 'report.md',
      byte_size: 42,
      content_type: 'text/markdown'
    }
  }
  let state = applyRuntimeEvent(createRuntimeState(), event)
  state = applyRuntimeEvent(state, event)

  assert.equal(state.artifacts.length, 1)
})

test('bounds and normalizes untrusted plan fields', () => {
  const steps = normalizePlanSteps([
    { title: 'x'.repeat(300), status: 'unknown' },
    ...Array.from({ length: 20 }, (_, index) => ({
      title: `Step ${index}`,
      status: 'pending'
    }))
  ])

  assert.equal(steps.length, 12)
  assert.equal(steps[0].title.length, 240)
  assert.equal(steps[0].status, 'pending')
})
