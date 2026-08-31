export function filterRoutingCandidates(assistants, query) {
  const normalizedQuery = String(query || '')
    .trim()
    .toLocaleLowerCase()
  if (!normalizedQuery) return assistants
  return assistants.filter((assistant) =>
    String(assistant.name || '')
      .toLocaleLowerCase()
      .includes(normalizedQuery)
  )
}

export function toggleRoutingScopeSelection(selectedUuids, assistants) {
  const candidateUuids = assistants.map((assistant) => assistant.uuid)
  const selected = new Set(selectedUuids)
  const allSelected =
    candidateUuids.length > 0 &&
    candidateUuids.every((uuid) => selected.has(uuid))
  return allSelected ? [] : candidateUuids
}
