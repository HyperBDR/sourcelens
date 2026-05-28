export const FEATURE_DEFINITIONS = [
  {
    key: 'workspace',
    labelKey: 'platforms.workspace',
    defaultPath: '/dashboard',
    matchers: ['/dashboard', '/settings']
  },
  {
    key: 'admin_console',
    labelKey: 'platforms.adminConsole',
    defaultPath: '/management/users',
    matchers: ['/management', '/llm', '/task-management', '/notifier']
  }
]

export const FEATURE_KEY_SET = new Set(
  FEATURE_DEFINITIONS.map((item) => item.key)
)

const FEATURE_MAP = new Map(FEATURE_DEFINITIONS.map((item) => [item.key, item]))

const FEATURE_ALIASES = {
  llm_console: 'admin_console',
  task_management_console: 'admin_console',
  notification_console: 'admin_console'
}

export function normalizeFeatureKeys(values) {
  if (!Array.isArray(values)) return []

  const seen = new Set()
  return FEATURE_DEFINITIONS.map((item) => item.key).filter((key) => {
    const matches = values.some((value) => {
      const normalized = FEATURE_ALIASES[value] || value
      return normalized === key
    })
    return matches && !seen.has(key) && seen.add(key)
  })
}

export function normalizePlatformKey(value) {
  const normalized = FEATURE_ALIASES[value] || value
  return FEATURE_KEY_SET.has(normalized) ? normalized : ''
}

export function getAccessProfile(user) {
  return (
    user?.access_profile || {
      visible_features: [],
      available_platforms: [],
      preferred_platform: '',
      landing_path: '/dashboard'
    }
  )
}

export function hasFeature(user, featureKey) {
  const normalizedFeatureKey = FEATURE_ALIASES[featureKey] || featureKey
  const visibleFeatures = normalizeFeatureKeys(
    getAccessProfile(user).visible_features
  )
  return visibleFeatures.includes(normalizedFeatureKey)
}

export function hasPermission(user, permission) {
  if (!permission) return true
  const permissions = Array.isArray(user?.permissions) ? user.permissions : []
  return permissions.includes(permission)
}

export function hasAnyPermission(user, permissions) {
  if (!Array.isArray(permissions) || permissions.length === 0) return true
  return permissions.some((permission) => hasPermission(user, permission))
}

export function getAvailablePlatforms(user, t) {
  const accessProfile = getAccessProfile(user)
  const platformMap = new Map(
    (accessProfile.available_platforms || []).map((item) => [item.key, item])
  )

  return FEATURE_DEFINITIONS.filter((item) => platformMap.has(item.key)).map(
    (item) => {
      const resolved = platformMap.get(item.key)
      return {
        key: item.key,
        label: t ? t(item.labelKey) : item.key,
        defaultPath: resolved?.default_path || item.defaultPath
      }
    }
  )
}

export function getLandingPath(user) {
  return getAccessProfile(user).landing_path || '/dashboard'
}

export function getCurrentPlatformKey(path) {
  const matched = FEATURE_DEFINITIONS.find((item) =>
    item.matchers.some((matcher) => path.startsWith(matcher))
  )
  return matched?.key || 'workspace'
}

export function getPlatformByKey(platformKey, t) {
  const definition = FEATURE_MAP.get(platformKey)
  if (!definition) return null
  return {
    key: definition.key,
    label: t ? t(definition.labelKey) : definition.key,
    defaultPath: definition.defaultPath
  }
}
