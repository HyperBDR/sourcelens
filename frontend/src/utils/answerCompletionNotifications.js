const UNREAD_STORAGE_KEY = 'sourcelens.answerCompletion.unreadSessions'
const NATIVE_NOTIFIED_RUNS_KEY =
  'sourcelens.answerCompletion.nativeNotifiedRuns'
const MAX_NATIVE_NOTIFIED_RUNS = 100
const TERMINAL_RUN_STATUSES = new Set(['done', 'failed', 'cancelled'])

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

function readArray(storage, key) {
  try {
    const value = JSON.parse(storage?.getItem(key) || '[]')
    return Array.isArray(value) ? value : []
  } catch {
    return []
  }
}

export function readUnreadSessions(storage) {
  return readObject(storage, UNREAD_STORAGE_KEY)
}

export function answerCompletionTitle({
  baseTitle,
  completionLabel,
  hasUnread
}) {
  return hasUnread ? `🔔 ${completionLabel} · ${baseTitle}` : baseTitle
}

export function shouldReviewUnreadSession({
  documentRef,
  selectedSessionUuid,
  unreadSessions
}) {
  return (
    documentRef?.visibilityState === 'visible' &&
    Boolean(selectedSessionUuid && unreadSessions?.[selectedSessionUuid])
  )
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

function reserveNativeNotification(storage, runUuid) {
  const notifiedRuns = readArray(storage, NATIVE_NOTIFIED_RUNS_KEY)
  if (notifiedRuns.includes(runUuid)) {
    return false
  }
  try {
    storage?.setItem(
      NATIVE_NOTIFIED_RUNS_KEY,
      JSON.stringify(
        [...notifiedRuns, runUuid].slice(-MAX_NATIVE_NOTIFIED_RUNS)
      )
    )
    return Boolean(storage)
  } catch {
    return false
  }
}

export async function requestNativeNotificationPermission(NotificationRef) {
  if (!NotificationRef) return null
  if (NotificationRef.permission !== 'default') {
    return NotificationRef.permission
  }
  try {
    return await NotificationRef.requestPermission()
  } catch {
    return null
  }
}

function showNativeCompletionNotification(options) {
  const nativeNotification = options.nativeNotification
  const NotificationRef = nativeNotification?.NotificationRef
  if (
    !nativeNotification?.enabled ||
    !isInactive(options.documentRef) ||
    NotificationRef?.permission !== 'granted' ||
    !reserveNativeNotification(options.storage, options.run.uuid)
  ) {
    return false
  }

  try {
    const notification = new NotificationRef(nativeNotification.title, {
      body: nativeNotification.body,
      renotify: false,
      tag: `sourcelens-answer-${options.run.uuid}`
    })
    notification.onclick = () => {
      try {
        notification.close()
        nativeNotification.windowRef?.focus?.()
        const opening = nativeNotification.onOpenConversation?.(
          options.sessionUuid
        )
        opening?.catch?.(() => {})
      } catch {
        return
      }
    }
    return true
  } catch {
    return false
  }
}

export function handleTerminalRun(options) {
  if (options.run?.status !== 'done') {
    return { nativeNotificationShown: false, unreadChanged: false }
  }

  const isAnotherConversation =
    options.sessionUuid !== options.selectedSessionUuid
  let unreadChanged = false
  if (
    options.indicatorEnabled &&
    (isAnotherConversation || isInactive(options.documentRef))
  ) {
    unreadChanged = markUnreadSession(
      options.storage,
      options.sessionUuid,
      options.run.uuid
    )
  }

  return {
    nativeNotificationShown: showNativeCompletionNotification(options),
    unreadChanged
  }
}

export async function pollRunUntilTerminal({
  getRun,
  initialRun,
  isStopped = () => false,
  maxAttempts,
  runUuid,
  sleep
}) {
  let run = initialRun
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (TERMINAL_RUN_STATUSES.has(run?.status)) {
      return run
    }
    if (isStopped()) return null
    await sleep()
    if (isStopped()) return null
    try {
      run = await getRun(runUuid)
    } catch {
      continue
    }
  }
  return TERMINAL_RUN_STATUSES.has(run?.status) ? run : null
}

export { UNREAD_STORAGE_KEY }
