export function credentialUrl(row) {
  const summary = row?.scope_summary || {}
  return (
    summary.organization_url ||
    summary.folder_url ||
    summary.folder_token ||
    row?.endpoint_url ||
    ''
  )
}

export function credentialUrlLabel(row) {
  const value = credentialUrl(row)
  if (!value) return ''

  try {
    const url = new URL(value)
    const parts = url.pathname.split('/').filter(Boolean)
    if (parts.length === 0) return url.hostname
    if (parts.length <= 2) {
      return `${url.hostname}/${parts.join('/')}`
    }
    return `${url.hostname}/…/${parts.at(-1)}`
  } catch {
    return value
  }
}

export function filterAndSortCredentials(rows, filters = {}) {
  const query = String(filters.query || '')
    .trim()
    .toLocaleLowerCase()
  const provider = filters.provider || 'all'
  const validationStatus = filters.validationStatus || 'all'

  const filtered = rows.filter((row) => {
    const rowValidationStatus = row?.validation_status || 'unchecked'
    const matchesQuery =
      !query ||
      [row?.name, row?.provider, row?.auth_type, credentialUrl(row)]
        .filter(Boolean)
        .some((value) => String(value).toLocaleLowerCase().includes(query))
    const matchesProvider = provider === 'all' || row?.provider === provider
    const matchesValidation =
      validationStatus === 'all' || rowValidationStatus === validationStatus
    return matchesQuery && matchesProvider && matchesValidation
  })

  if (filters.sort === 'name_asc') {
    return [...filtered].sort((left, right) =>
      String(left?.name || '').localeCompare(String(right?.name || ''))
    )
  }
  if (filters.sort === 'last_used_desc') {
    return sortByDateDescending(filtered, 'last_used_at')
  }
  if (filters.sort === 'validated_desc') {
    return sortByDateDescending(filtered, 'validated_at')
  }
  return filtered
}

export function formatCredentialDateTime(value, locale, timeZone) {
  if (!value) return ''
  return new Intl.DateTimeFormat(locale, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone,
    timeZoneName: 'short'
  }).format(new Date(value))
}

function sortByDateDescending(rows, field) {
  return [...rows].sort((left, right) => {
    const leftTime = left?.[field] ? new Date(left[field]).getTime() : 0
    const rightTime = right?.[field] ? new Date(right[field]).getTime() : 0
    return rightTime - leftTime
  })
}
