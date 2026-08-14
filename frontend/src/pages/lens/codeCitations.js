export function citationLocation(citation = {}) {
  const path = citation.path || ''
  const start = Number(citation.start_line) || 1
  const end = Number(citation.end_line) || start
  return end === start ? `${path}:${start}` : `${path}:${start}-${end}`
}

export function citationSourceUrl(runUuid, citationId) {
  return `/lens/runs/${encodeURIComponent(runUuid)}/citations/${encodeURIComponent(
    citationId
  )}/`
}
