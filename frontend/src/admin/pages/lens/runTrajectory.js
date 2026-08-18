export function eventCategory(event) {
  return String(event?.event_type || '').split('.', 1)[0] || 'other'
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

export function buildTrajectoryRows(events, collapsed) {
  const parentByCall = new Map()
  const childParents = new Set()
  for (const event of events) {
    if (event.call_id && event.parent_call_id) {
      parentByCall.set(event.call_id, event.parent_call_id)
      childParents.add(event.parent_call_id)
    }
  }
  return events.flatMap((event) => {
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
        hasChildren: Boolean(event.call_id && childParents.has(event.call_id))
      }
    ]
  })
}
