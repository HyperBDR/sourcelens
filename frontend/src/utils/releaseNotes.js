export const RELEASE_NOTES_STORAGE_KEY =
  'sourcelens.releaseNotes.lastViewedVersion'

const CATEGORY_ORDER = ['feature', 'improvement', 'fix']

function browserStorage() {
  return typeof window === 'undefined' ? null : window.localStorage
}

function isEntryVisible(entry, isAdmin) {
  return entry?.audience === 'user' || (isAdmin && entry?.audience === 'admin')
}

export function getReleaseNotesStorageKey(isAdmin = false) {
  const audience = isAdmin ? 'admin' : 'user'
  return `${RELEASE_NOTES_STORAGE_KEY}.${audience}`
}

export function selectLocalizedReleaseNotes(manifest, locale, isAdmin = false) {
  const language = locale === 'zh-CN' ? 'zh-CN' : 'en'
  const categories = manifest?.categories || {}

  return CATEGORY_ORDER.map((type) => {
    const entries = Array.isArray(categories[type]) ? categories[type] : []
    return {
      type,
      entries: entries
        .filter((entry) => isEntryVisible(entry, isAdmin))
        .map((entry) => ({
          audience: entry.audience,
          text: entry?.[language] || entry?.en || ''
        }))
        .filter((entry) => entry.text)
    }
  }).filter((group) => group.entries.length > 0)
}

export function hasReleaseNotesForAudience(manifest, isAdmin = false) {
  const categories = manifest?.categories || {}
  return CATEGORY_ORDER.some((type) => {
    const entries = Array.isArray(categories[type]) ? categories[type] : []
    return entries.some((entry) => isEntryVisible(entry, isAdmin))
  })
}

export function hasUnreadReleaseNotes(
  version,
  storage = browserStorage(),
  isAdmin = false
) {
  if (!storage) return false
  return isReleaseNotesVersionUnread(
    version,
    storage.getItem(getReleaseNotesStorageKey(isAdmin))
  )
}

export function isReleaseNotesVersionUnread(version, viewedVersion) {
  if (!version || version === 'dev') return false
  return viewedVersion !== version
}

export function markReleaseNotesViewed(
  version,
  storage = browserStorage(),
  isAdmin = false
) {
  if (!version || version === 'dev' || !storage) return
  storage.setItem(getReleaseNotesStorageKey(isAdmin), version)
}
