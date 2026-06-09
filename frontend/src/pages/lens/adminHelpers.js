/**
 * Pure helpers shared by the Lens admin page and its sub-components.
 *
 * These functions depend only on their arguments (no component state, no
 * i18n), so they live outside the SFC to keep Admin.vue focused on
 * orchestration.
 */

export const EMPTY_VALUE = '—'

export function compactUuid(value) {
  if (!value) {
    return EMPTY_VALUE
  }
  return `${String(value).slice(0, 8)}...${String(value).slice(-6)}`
}

export function formatTaskName(row) {
  return row.name || row.task_name || row.task_type || EMPTY_VALUE
}

export function formatLLMConfigLabel(config) {
  const model = config.config?.model || config.model || EMPTY_VALUE
  return `${config.provider || config.name || config.uuid} · ${model}`
}

export function splitList(value) {
  return String(value || '')
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
}

export function listToText(value) {
  return Array.isArray(value) ? value.join(',') : ''
}

export function objectToRows(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return []
  }
  return Object.entries(value).map(([key, rowValue]) => ({
    key,
    value: typeof rowValue === 'string' ? rowValue : String(rowValue)
  }))
}

export function stringifyJson(value) {
  return JSON.stringify(value, null, 2)
}

export function rowsToObject(rows) {
  return (rows || []).reduce((output, row) => {
    const key = String(row.key || '').trim()
    if (key) {
      output[key] = String(row.value || '').trim()
    }
    return output
  }, {})
}

export function selectedDirsFromValue(value) {
  if (!Array.isArray(value)) {
    return []
  }
  return value
    .map((dir) => ({
      path: dir.path || '',
      include_paths_text: (
        dir.retrieval_scope?.include_paths ||
        dir.include_paths ||
        []
      ).join('\n')
    }))
    .filter((dir) => dir.path)
}

export function normalizeList(payload) {
  if (Array.isArray(payload)) {
    return payload
  }
  if (Array.isArray(payload?.results)) {
    return payload.results
  }
  return []
}
