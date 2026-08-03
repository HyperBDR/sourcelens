import {
  buildSkillEnvironment,
  skillEnvironmentForm
} from './skillEnvironment.js'

export const MCP_CONFIG_MASK = '********'

const SENSITIVE_KEY_NAMES = new Set([
  'apikey',
  'authorization',
  'credential',
  'credentials',
  'password',
  'passwd',
  'privatekey',
  'secret',
  'token'
])

const SENSITIVE_KEY_SEGMENTS = new Set([
  'authorization',
  'credential',
  'credentials',
  'password',
  'passwd',
  'secret'
])

export function isSensitiveMcpConfigKey(key) {
  const rawKey = String(key || '')
  const normalized = rawKey.toLocaleLowerCase().replace(/[^a-z0-9]/g, '')
  if (SENSITIVE_KEY_NAMES.has(normalized)) return true

  const segmentedKey = rawKey.replace(/([a-z0-9])([A-Z])/g, '$1_$2')
  const segments = (segmentedKey.match(/[A-Za-z0-9]+/g) || []).map((segment) =>
    segment.toLocaleLowerCase()
  )
  if (segments.some((segment) => SENSITIVE_KEY_SEGMENTS.has(segment))) {
    return true
  }
  if (
    segments.some(
      (segment, index) =>
        (segment === 'api' || segment === 'private') &&
        segments[index + 1] === 'key'
    )
  ) {
    return true
  }
  return segments.at(-1) === 'token'
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
    if (row.serialized === false) {
      output[key] = value
      return output
    }
    if (row.serialized !== true) {
      output[key] = parseJsonContainer(value)
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

function parseJsonContainer(value) {
  if (!value.startsWith('{') && !value.startsWith('[')) return value
  try {
    const parsed = JSON.parse(value)
    return parsed !== null && typeof parsed === 'object' ? parsed : value
  } catch {
    return value
  }
}

export function mcpEnvironmentForm(declarations = []) {
  return skillEnvironmentForm(declarations).map((item, index) => ({
    ...item,
    required: declarations[index]?.required !== false
  }))
}

export function buildMcpEnvironment(items = []) {
  return buildSkillEnvironment(items).map((item, index) => ({
    ...item,
    required: items[index]?.required !== false
  }))
}
