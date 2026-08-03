export const MCP_CONFIG_MASK = '********'

const SENSITIVE_KEY_FRAGMENTS = [
  'apikey',
  'authorization',
  'credential',
  'password',
  'passwd',
  'privatekey',
  'secret',
  'token'
]

export function isSensitiveMcpConfigKey(key) {
  const normalized = String(key || '')
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]/g, '')
  return SENSITIVE_KEY_FRAGMENTS.some((fragment) =>
    normalized.includes(fragment)
  )
}

export function mcpConfigToRows(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return []
  }
  return Object.entries(value).map(([key, rowValue]) => ({
    key,
    value: typeof rowValue === 'string' ? rowValue : JSON.stringify(rowValue),
    serialized: typeof rowValue !== 'string'
  }))
}

export function mcpRowsToConfig(rows) {
  return (rows || []).reduce((output, row) => {
    const key = String(row.key || '').trim()
    if (!key) return output
    const value = String(row.value || '').trim()
    if (!row.serialized) {
      output[key] = value
      return output
    }
    try {
      output[key] = JSON.parse(value)
    } catch {
      output[key] = value
    }
    return output
  }, {})
}
