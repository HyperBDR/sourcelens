export function eventCategory(event) {
  return String(event?.event_type || '').split('.', 1)[0] || 'other'
}

const INSPECTOR_MIN_WIDTH = 320
const LEDGER_MIN_WIDTH = 420

export function clampInspectorWidth(splitWidth, desiredWidth) {
  const maxWidth = Math.max(0, splitWidth - LEDGER_MIN_WIDTH)
  const minWidth = Math.min(INSPECTOR_MIN_WIDTH, maxWidth)
  return Math.min(Math.max(desiredWidth, minWidth), maxWidth)
}

export function timelineLane(category) {
  if (category === 'model') return 'model'
  if (category === 'tool' || category === 'subtool') return 'tools'
  return 'input'
}

export function isSubagentEvent(category, event) {
  const payload = event?.payload || {}
  if (category === 'model') return payload.is_subagent === true
  return String(payload.name || '') === 'task'
}

function eventTime(event) {
  if (event._ms !== undefined && Number.isFinite(event._ms)) return event._ms
  return new Date(event.timestamp).getTime()
}

export function buildTimelineLanes(events, summary) {
  const first = new Date(summary?.first_timestamp).getTime()
  const last = new Date(summary?.last_timestamp).getTime()
  const total = last - first
  if (!Number.isFinite(total) || total <= 0) {
    return [
      { key: 'input', steps: [] },
      { key: 'model', steps: [] },
      { key: 'tools', steps: [] }
    ]
  }

  const byCall = new Map()
  for (const event of events) {
    if (event.call_id) {
      const list = byCall.get(event.call_id) || []
      list.push(event)
      byCall.set(event.call_id, list)
    }
  }

  const stepsByLane = { input: [], model: [], tools: [] }

  function pushStep(category, event, startMs, endMs, subagent, seqs = []) {
    const lane = timelineLane(category)
    const left = Math.max(0, Math.min(99.5, ((startMs - first) / total) * 100))
    const rawWidth = ((endMs - startMs) / total) * 100
    const width = Math.max(rawWidth, 0.6)
    stepsByLane[lane].push({
      event,
      left,
      width: Math.min(width, 100 - left),
      subagent,
      assistantName: event.assistant_name || null,
      startMs,
      durationMs: endMs - startMs,
      seqs: seqs.length > 0 ? seqs : [event.sequence]
    })
  }

  for (const group of byCall.values()) {
    const category = eventCategory(group[0])
    if (!['model', 'tool', 'subtool'].includes(category)) continue
    const times = group.map(eventTime).filter(Number.isFinite)
    if (!times.length) continue
    const subagent = group.some(
      (event) =>
        event.trace_run_role === 'child' || isSubagentEvent(category, event)
    )
    pushStep(
      category,
      group[0],
      Math.min(...times),
      Math.max(...times),
      subagent,
      group.map((event) => event.sequence)
    )
  }

  for (const event of events) {
    const category = eventCategory(event)
    const inCallGroup =
      Boolean(event.call_id) && ['model', 'tool', 'subtool'].includes(category)
    if (inCallGroup) continue
    const startMs = eventTime(event)
    if (!Number.isFinite(startMs)) continue
    pushStep(category, event, startMs, startMs, false)
  }

  return [
    { key: 'input', steps: stepsByLane.input },
    { key: 'model', steps: stepsByLane.model },
    { key: 'tools', steps: stepsByLane.tools }
  ]
}

export function buildTimelineGroups(
  events,
  summary,
  parentLabel = 'Parent Run'
) {
  const groups = new Map()
  for (const event of events) {
    const isChild = event.trace_run_role === 'child'
    const label = isChild ? event.assistant_name || 'Subagent' : parentLabel
    const key = isChild ? `child:${label}` : 'parent'
    const group = groups.get(key) || { key, label, events: [] }
    group.events.push(event)
    groups.set(key, group)
  }

  const laneLabels = { input: 'Input', model: 'Model', tools: 'Tools' }
  return [...groups.values()].flatMap((group) =>
    buildTimelineLanes(group.events, summary).map((lane) => ({
      ...lane,
      key: `${group.key}:${lane.key}`,
      groupKey: group.key,
      groupLabel: group.label,
      label: laneLabels[lane.key]
    }))
  )
}

function eventDepth(event, parentByCall) {
  let parent = event.parent_call_id
  let depth = 0
  const seen = new Set()
  while (parent && !seen.has(parent) && depth < 8) {
    seen.add(parent)
    depth += 1
    parent = parentByCall.get(parent) || ''
  }
  return depth
}

function sequenceValue(event) {
  const value = Number(event?.sequence)
  return Number.isFinite(value) ? value : null
}

export function sortTrajectoryEvents(events) {
  return events
    .map((event, index) => ({ event, index, sequence: sequenceValue(event) }))
    .sort((left, right) => {
      if (left.sequence === null && right.sequence === null) {
        return left.index - right.index
      }
      if (left.sequence === null) return 1
      if (right.sequence === null) return -1
      return left.sequence - right.sequence || left.index - right.index
    })
    .map(({ event }) => event)
}

export function buildTrajectoryRows(events, collapsed) {
  const orderedEvents = sortTrajectoryEvents(events)
  const parentByCall = new Map()
  const childParents = new Set()
  const firstEventByCall = new Map()
  for (const event of orderedEvents) {
    if (event.call_id && !firstEventByCall.has(event.call_id)) {
      firstEventByCall.set(event.call_id, event)
    }
    if (event.call_id && event.parent_call_id) {
      parentByCall.set(event.call_id, event.parent_call_id)
      childParents.add(event.parent_call_id)
    }
  }
  return orderedEvents.flatMap((event) => {
    let parent = event.parent_call_id
    const seen = new Set()
    while (parent && !seen.has(parent)) {
      if (collapsed.has(parent)) return []
      seen.add(parent)
      parent = parentByCall.get(parent) || ''
    }
    return [
      {
        event,
        depth: eventDepth(event, parentByCall),
        hasChildren: Boolean(
          event.call_id &&
            childParents.has(event.call_id) &&
            firstEventByCall.get(event.call_id) === event
        )
      }
    ]
  })
}

const STEP_STATUS_SUFFIX = /\.(start|started|done|completed|failed|stopped)$/

function stepGroupName(event) {
  const name = String(event?.payload?.name || '')
  if (!name) return 'step'
  return name.replace(STEP_STATUS_SUFFIX, '')
}

export function groupTrajectoryRows(rows) {
  const groups = []
  const index = new Map()
  for (const row of rows) {
    const category = eventCategory(row.event)
    let key = category
    let label = category
    if (category === 'step') {
      key = `step:${stepGroupName(row.event)}`
      label = stepGroupName(row.event)
    }
    if (!index.has(key)) {
      const group = { key, category, label, rows: [] }
      index.set(key, group)
      groups.push(group)
    }
    index.get(key).rows.push(row)
  }
  return groups
}
