const PLAN_STATUSES = new Set(['pending', 'in_progress', 'completed'])
const STAGE_STATUSES = new Set([
  'pending',
  'in_progress',
  'completed',
  'failed',
  'skipped'
])
const ACTIVITY_STATUSES = new Set(['in_progress', 'completed', 'failed'])
const STRUCTURED_ACTIVITY_KINDS = new Set([
  'query_orders',
  'get_order_detail',
  'reading_order_commands',
  'checking_capability',
  'querying_data',
  'count_results',
  'group_results',
  'analyzing_results',
  'analyzing_request'
])
const WORKFLOW_STAGE_KINDS = new Set([
  'order_query',
  'data_query',
  'result_analysis',
  'reasoning'
])

export function calculateRunElapsedSeconds(run, nowMs = Date.now()) {
  const createdMs = Date.parse(run?.created_at || '')
  if (!Number.isFinite(createdMs) || !Number.isFinite(nowMs)) return 0

  const finishedMs = run?.finished_at ? Date.parse(run.finished_at) : nowMs
  if (!Number.isFinite(finishedMs)) return 0

  return Math.max(0, Math.floor((finishedMs - createdMs) / 1000))
}

export function getMessageTimestamp(message) {
  if (message?.role === 'assistant' && message.completed_at) {
    return message.completed_at
  }
  return message?.created_at || ''
}

export async function scrollConversationToBottomAfterRender(
  getElement,
  waitForRender
) {
  await waitForRender()
  const element = getElement()
  if (!element) return false
  element.scrollTop = element.scrollHeight
  return true
}

export function createRuntimeState() {
  return {
    route: null,
    complexity: null,
    evidenceRequirement: null,
    phase: null,
    plan: [],
    planRevision: 0,
    stages: [],
    stageRevision: 0,
    activities: [],
    activityRevision: 0,
    capabilityBlock: null,
    executionFailure: null,
    artifacts: [],
    outcome: null,
    terminationDetail: null
  }
}

function activityKindForEvent(event) {
  const agentEvent = String(event?.agent_event || '')
  if (!agentEvent.startsWith('tool.')) return null
  if (!(agentEvent.endsWith('.invoke') || agentEvent.endsWith('.start'))) {
    return null
  }

  const toolName = agentEvent.slice(5).replace(/\.(invoke|start)$/, '')
  if (
    [
      'analyze_structured_output',
      'inspect_saved_output',
      'run_skill_transform'
    ].includes(toolName)
  ) {
    return 'analyzingResults'
  }
  if (
    toolName === 'run_skill_artifact' ||
    toolName === 'call_skill_api' ||
    toolName.startsWith('mcp__')
  ) {
    return 'queryingData'
  }
  if (['read_file', 'ls'].includes(toolName)) return 'readingContext'
  if (['search_workspace', 'find_files'].includes(toolName)) {
    return 'searchingSources'
  }
  if (
    [
      'read_workspace_file',
      'git_diff',
      'git_log',
      'summarize_recent_changes'
    ].includes(toolName)
  ) {
    return 'readingSources'
  }
  if (['write_file', 'save_deliverable'].includes(toolName)) {
    return 'preparingOutput'
  }
  if (toolName === 'tool_search') return 'findingCapability'
  return 'usingCapability'
}

function activeNodeId(state) {
  const planStep = state.plan.find((item) => item.status === 'in_progress')
  if (planStep) return planStep.id
  return state.stages.find((item) => item.status === 'in_progress')?.id || ''
}

function appendActivity(state, kind) {
  const nodeId = activeNodeId(state)
  if (!nodeId) return state
  const last = state.activities[state.activities.length - 1]
  if (last?.nodeId === nodeId && last.kind === kind) {
    return {
      ...state,
      activities: [
        ...state.activities.slice(0, -1),
        { ...last, count: last.count + 1 }
      ]
    }
  }
  const activityRevision = state.activityRevision + 1
  return {
    ...state,
    activityRevision,
    activities: capActivities([
      ...state.activities,
      { id: activityRevision, nodeId, kind, count: 1 }
    ])
  }
}

function capActivities(activities) {
  const structured = activities.filter((item) => item.structured).slice(-120)
  const generic = activities.filter((item) => !item.structured).slice(-20)
  return activities.filter(
    (item) => structured.includes(item) || generic.includes(item)
  )
}

function normalizeActivityDate(value) {
  const date = String(value || '')
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return ''
  const parsed = new Date(`${date}T00:00:00Z`)
  if (Number.isNaN(parsed.getTime())) return ''
  return parsed.toISOString().slice(0, 10) === date ? date : ''
}

function appendStructuredActivity(state, payload) {
  if (!payload || typeof payload !== 'object') return state
  const id = String(payload.id || '')
    .trim()
    .slice(0, 64)
  if (!/^[A-Za-z0-9_-]+$/.test(id)) return state
  if (!STRUCTURED_ACTIVITY_KINDS.has(payload.kind)) return state
  if (!WORKFLOW_STAGE_KINDS.has(payload.stage_kind)) return state
  if (!ACTIVITY_STATUSES.has(payload.status)) return state

  const existing = state.activities.find(
    (item) => item.structured && item.id === id
  )
  const startDate = normalizeActivityDate(payload.start_date)
  const endDate = normalizeActivityDate(payload.end_date)
  const round = Math.min(Math.max(Number(payload.round || 0), 0), 100)
  const activeTask = state.plan.find((item) => item.status === 'in_progress')
  const taskId = existing?.taskId || activeTask?.id || 'task-execute'
  const stageKind = existing?.stageKind || payload.stage_kind
  const activity = {
    id,
    taskId,
    stageId: `${taskId}:${stageKind}`,
    stageKind,
    kind:
      existing?.kind && existing.kind !== 'querying_data'
        ? existing.kind
        : payload.kind,
    status:
      existing?.status === 'completed' && payload.status === 'in_progress'
        ? existing.status
        : payload.status,
    ...(existing?.round || round ? { round: existing?.round || round } : {}),
    ...(existing?.startDate || startDate
      ? { startDate: existing?.startDate || startDate }
      : {}),
    ...(existing?.endDate || endDate
      ? { endDate: existing?.endDate || endDate }
      : {}),
    structured: true
  }
  const activities = existing
    ? state.activities.map((item) =>
        item.structured && item.id === id ? activity : item
      )
    : [...state.activities, activity]
  return {
    ...state,
    activityRevision: state.activityRevision + 1,
    activities: capActivities(activities)
  }
}

function closeRuntimeProgress(state, status) {
  const activities = state.activities.map((item) => {
    if (!item.structured || item.status !== 'in_progress') return item
    return { ...item, status }
  })
  const stages = state.stages.map((item) => {
    if (item.status === 'in_progress') return { ...item, status }
    if (item.status === 'pending') return { ...item, status: 'skipped' }
    return item
  })
  const plan = state.plan.map((item) => {
    if (item.status === 'in_progress') return { ...item, status }
    if (item.status === 'pending') return { ...item, status: 'skipped' }
    return item
  })
  return { ...state, activities, stages, plan }
}

export function activitiesForNode(state, nodeId) {
  return (state?.activities || []).filter((item) => item.nodeId === nodeId)
}

export function normalizeStages(stages) {
  if (!Array.isArray(stages)) return []
  return stages.slice(0, 12).flatMap((item, index) => {
    if (!item || typeof item !== 'object') return []
    const id = String(item.id || '')
      .trim()
      .slice(0, 64)
    const title = String(item.title || '')
      .trim()
      .slice(0, 240)
    if (!id || !title || !STAGE_STATUSES.has(item.status)) return []
    const numericOrder = Number(item.order)
    const order = Number.isFinite(numericOrder)
      ? Math.min(Math.max(Math.trunc(numericOrder), 1), 12)
      : index + 1
    return [
      {
        id,
        title,
        status: item.status,
        summary: String(item.summary || '')
          .trim()
          .slice(0, 240),
        order
      }
    ]
  })
}

export function normalizePlanSteps(steps) {
  if (!Array.isArray(steps)) return []
  return steps.slice(0, 12).flatMap((item, index) => {
    if (!item || typeof item !== 'object') return []
    const title = String(item.title || '')
      .trim()
      .slice(0, 240)
    if (!title) return []
    const status = PLAN_STATUSES.has(item.status) ? item.status : 'pending'
    return [
      {
        id: String(item.id || `step-${index + 1}`).slice(0, 64),
        title,
        status
      }
    ]
  })
}

export function summarizePlanProgress(steps, { terminal = false } = {}) {
  if (!Array.isArray(steps) || steps.length === 0) return null
  const completed = steps.filter((step) => step.status === 'completed').length
  const current =
    steps.find((step) => step.status === 'in_progress') ||
    steps.find((step) => step.status === 'pending')
  return {
    completed,
    total: steps.length,
    currentTitle: current?.title || '',
    isComplete: completed === steps.length,
    isTerminal: terminal
  }
}

export function summarizeStageProgress(stages, { terminal = false } = {}) {
  if (!Array.isArray(stages) || stages.length === 0) return null
  const completed = stages.filter(
    (stage) => stage.status === 'completed'
  ).length
  const current =
    stages.find((stage) => stage.status === 'in_progress') ||
    stages.find((stage) => stage.status === 'failed') ||
    stages.find((stage) => stage.status === 'pending')
  return {
    completed,
    total: stages.length,
    currentTitle: current?.title || '',
    currentSummary: current?.summary || '',
    isComplete: stages.every((stage) =>
      ['completed', 'skipped'].includes(stage.status)
    ),
    isTerminal: terminal
  }
}

export function selectLiveProgressText({
  planProgressText,
  stageProgressText,
  latestStep,
  phaseText,
  activityMessage,
  fallbackText
}) {
  return (
    planProgressText ||
    stageProgressText ||
    phaseText ||
    latestStep ||
    activityMessage ||
    fallbackText
  )
}

function workflowNodeStatus(items) {
  if (items.some((item) => item.status === 'in_progress')) {
    return 'in_progress'
  }
  if (items.some((item) => item.status === 'failed')) return 'failed'
  return items.length > 0 ? 'completed' : 'pending'
}

export function buildWorkflowTree(plan, activities) {
  const tasks = (Array.isArray(plan) ? plan : []).map((item, index) => ({
    ...item,
    order: index + 1,
    stages: []
  }))
  const taskById = new Map(tasks.map((item) => [item.id, item]))
  for (const step of Array.isArray(activities) ? activities : []) {
    if (!step?.structured || !step.taskId || !step.stageId) continue
    let task = taskById.get(step.taskId)
    if (!task) {
      task = {
        id: step.taskId,
        kind: 'execute_request',
        order: tasks.length + 1,
        status: 'pending',
        stages: []
      }
      tasks.push(task)
      taskById.set(task.id, task)
    }
    let stage = task.stages.find((item) => item.id === step.stageId)
    if (!stage) {
      stage = {
        id: step.stageId,
        kind: step.stageKind,
        order: task.stages.length + 1,
        status: 'pending',
        steps: []
      }
      task.stages.push(stage)
    }
    stage.steps.push(step)
  }
  for (const task of tasks) {
    for (const stage of task.stages) {
      stage.status = workflowNodeStatus(stage.steps)
    }
    if (!task.title) {
      task.status = workflowNodeStatus(task.stages)
    }
  }
  return tasks
}

export function selectStructuredProgress({ route, plan, stages, activities }) {
  if (route) {
    const tasks = buildWorkflowTree(plan, activities)
    if (tasks.length > 0) {
      return {
        kind: 'workflow',
        hasPlan: Array.isArray(plan) && plan.length > 0,
        items: tasks,
        tasks
      }
    }
    return { kind: null, items: [] }
  }
  if (Array.isArray(plan) && plan.length > 0) {
    return { kind: 'plan', items: plan }
  }
  if (Array.isArray(stages) && stages.length > 0) {
    return { kind: 'stage', items: stages }
  }
  return { kind: null, items: [] }
}

export function selectCurrentWorkflowStage(tasks) {
  const stages = (Array.isArray(tasks) ? tasks : []).flatMap(
    (task) => task.stages || []
  )
  if (stages.length === 0) return null
  for (const status of ['in_progress', 'failed']) {
    for (let index = stages.length - 1; index >= 0; index -= 1) {
      if (stages[index]?.status === status) return stages[index]
    }
  }
  return stages.at(-1) || null
}

export function applyRuntimeEvent(state, event) {
  const current = state || createRuntimeState()
  if (
    event?.type === 'sync' ||
    event?.type === 'done' ||
    event?.type === 'error'
  ) {
    const terminationDetail =
      event.termination_detail || current.terminationDetail
    const terminal = {
      ...current,
      outcome: event.outcome || current.outcome,
      terminationDetail,
      capabilityBlock:
        terminationDetail?.reason === 'capability_unavailable'
          ? { ...terminationDetail }
          : current.capabilityBlock,
      executionFailure:
        terminationDetail?.reason === 'execution_failed'
          ? { ...terminationDetail }
          : current.executionFailure
    }
    if (event.type === 'done') {
      const status = event.outcome === 'completed' ? 'completed' : 'failed'
      return closeRuntimeProgress(terminal, status)
    }
    if (event.type === 'error') {
      return closeRuntimeProgress(terminal, 'failed')
    }
    return terminal
  }
  if (
    event?.visibility === 'user' &&
    event.event_type === 'activity.recorded'
  ) {
    return appendStructuredActivity(current, event.payload)
  }
  const activityKind = activityKindForEvent(event)
  if (activityKind) return appendActivity(current, activityKind)
  if (event?.visibility !== 'user') return current
  const payload = event.payload || {}
  if (event.event_type === 'route.selected') {
    return {
      ...current,
      route: payload.route || null,
      complexity: payload.complexity || null,
      evidenceRequirement: payload.evidence_requirement || null
    }
  }
  if (event.event_type === 'phase.changed') {
    return { ...current, phase: payload.phase || null }
  }
  if (event.event_type === 'plan.updated') {
    const revision = Math.max(Number(payload.revision || 0), 0)
    if (revision < current.planRevision) return current
    return {
      ...current,
      plan: normalizePlanSteps(payload.steps),
      planRevision: revision
    }
  }
  if (event.event_type === 'stage.updated') {
    const revision = Math.max(Number(payload.revision || 0), 0)
    if (revision < current.stageRevision) return current
    const normalized = normalizeStages([payload])
    if (normalized.length === 0) return current
    const stage = normalized[0]
    const stages = current.stages.filter((item) => item.id !== stage.id)
    stages.push(stage)
    stages.sort((left, right) => left.order - right.order)
    return {
      ...current,
      stages,
      stageRevision: revision
    }
  }
  if (event.event_type === 'capability.blocked') {
    return { ...current, capabilityBlock: { ...payload } }
  }
  if (event.event_type === 'execution.failed') {
    return { ...current, executionFailure: { ...payload } }
  }
  if (event.event_type === 'artifact.created') {
    const artifact = {
      filename: String(payload.filename || ''),
      byteSize: Number(payload.byte_size || 0),
      contentType: String(payload.content_type || '')
    }
    const replayed = current.artifacts.some(
      (item) =>
        item.filename === artifact.filename &&
        item.byteSize === artifact.byteSize &&
        item.contentType === artifact.contentType
    )
    if (replayed) return current
    return { ...current, artifacts: [...current.artifacts, artifact] }
  }
  return current
}
