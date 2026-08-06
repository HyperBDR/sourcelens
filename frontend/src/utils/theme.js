export const THEME_MODES = ['light', 'dark', 'system', 'scheduled']

export const normalizeThemeMode = (value) =>
  THEME_MODES.includes(value) ? value : 'system'

export const isManagementPath = (pathname) => {
  if (typeof pathname !== 'string') return false
  const path = pathname.split(/[?#]/, 1)[0]
  return path === '/management' || path.startsWith('/management/')
}

export const resolveTheme = (mode, now, systemPrefersDark) => {
  const normalizedMode = normalizeThemeMode(mode)

  if (normalizedMode === 'scheduled') {
    const hour = now.getHours()
    return hour >= 20 || hour < 7 ? 'dark' : 'light'
  }
  if (normalizedMode === 'system') {
    return systemPrefersDark ? 'dark' : 'light'
  }

  return normalizedMode
}

export const getNextThemeBoundary = (now) => {
  const boundary = new Date(now)
  const hour = now.getHours()

  if (hour < 7) {
    boundary.setHours(7, 0, 0, 0)
  } else if (hour < 20) {
    boundary.setHours(20, 0, 0, 0)
  } else {
    boundary.setDate(boundary.getDate() + 1)
    boundary.setHours(7, 0, 0, 0)
  }

  return boundary
}
