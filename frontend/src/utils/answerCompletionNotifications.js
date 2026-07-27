const UNREAD_STORAGE_KEY = 'sourcelens.answerCompletion.unreadSessions'
const NOTIFIED_STORAGE_KEY = 'sourcelens.answerCompletion.notifiedRuns'
const MAX_NOTIFIED_RUNS = 100

function readObject(storage, key) {
  try {
    const value = JSON.parse(storage?.getItem(key) || '{}')
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value
      : {}
  } catch {
    return {}
  }
}

function writeObject(storage, key, value) {
  storage?.setItem(key, JSON.stringify(value))
}

export function browserNotificationState({
  enabled,
  isSecureContext,
  notificationApi
}) {
  if (!isSecureContext || !notificationApi) {
    return 'unsupported'
  }
  if (notificationApi.permission === 'denied') {
    return 'blocked'
  }
  if (enabled && notificationApi.permission === 'granted') {
    return 'enabled'
  }
  return 'disabled'
}

export async function enableBrowserNotifications({
  isSecureContext,
  notificationApi
}) {
  const state = browserNotificationState({
    enabled: false,
    isSecureContext,
    notificationApi
  })
  if (state === 'unsupported' || state === 'blocked') {
    return state
  }
  if (notificationApi.permission === 'granted') {
    return 'enabled'
  }

  try {
    const permission = await notificationApi.requestPermission()
    if (permission === 'granted') return 'enabled'
    if (permission === 'denied') return 'blocked'
  } catch {
    return 'disabled'
  }
  return 'disabled'
}

export function readUnreadSessions(storage) {
  return readObject(storage, UNREAD_STORAGE_KEY)
}

function markUnreadSession(storage, sessionUuid, runUuid) {
  const unread = readUnreadSessions(storage)
  if (unread[sessionUuid] === runUuid) {
    return false
  }
  unread[sessionUuid] = runUuid
  writeObject(storage, UNREAD_STORAGE_KEY, unread)
  return true
}

export function clearUnreadSession(storage, sessionUuid) {
  const unread = readUnreadSessions(storage)
  if (!(sessionUuid in unread)) {
    return false
  }
  delete unread[sessionUuid]
  writeObject(storage, UNREAD_STORAGE_KEY, unread)
  return true
}

function isInactive(documentRef) {
  return (
    documentRef?.visibilityState !== 'visible' ||
    documentRef?.hasFocus?.() === false
  )
}

function rememberNotifiedRun(storage, runUuid, now) {
  const notified = readObject(storage, NOTIFIED_STORAGE_KEY)
  if (notified[runUuid]) {
    return false
  }

  notified[runUuid] = now
  const recent = Object.entries(notified)
    .sort((left, right) => right[1] - left[1])
    .slice(0, MAX_NOTIFIED_RUNS)
  writeObject(storage, NOTIFIED_STORAGE_KEY, Object.fromEntries(recent))
  return true
}

async function sendBrowserNotification(options) {
  const send = () => {
    if (!rememberNotifiedRun(options.storage, options.runUuid, options.now)) {
      return false
    }

    try {
      const notification = new options.notificationApi(options.title, {
        icon: options.icon,
        tag: `sourcelens-answer-${options.runUuid}`
      })
      notification.onclick = () => {
        options.onOpen()
        notification.close()
      }
      return true
    } catch {
      return false
    }
  }

  if (options.locks?.request) {
    return options.locks.request(`sourcelens-answer-${options.runUuid}`, send)
  }
  return send()
}

export async function handleTerminalRun(options) {
  if (options.run?.status !== 'done') {
    return { browserNotified: false, unreadChanged: false }
  }

  const unreadChanged =
    options.indicatorEnabled &&
    options.sessionUuid !== options.selectedSessionUuid
      ? markUnreadSession(
          options.storage,
          options.sessionUuid,
          options.run.uuid
        )
      : false

  const state = browserNotificationState({
    enabled: options.browserEnabled,
    isSecureContext: options.isSecureContext,
    notificationApi: options.notificationApi
  })
  if (state !== 'enabled' || !isInactive(options.documentRef)) {
    return { browserNotified: false, unreadChanged }
  }

  const browserNotified = await sendBrowserNotification({
    icon: options.icon,
    locks: options.locks,
    notificationApi: options.notificationApi,
    now: options.now ?? Date.now(),
    onOpen: options.onOpen,
    runUuid: options.run.uuid,
    storage: options.storage,
    title: options.title
  })
  return { browserNotified, unreadChanged }
}

export { UNREAD_STORAGE_KEY }
