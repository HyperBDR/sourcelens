const UNREAD_STORAGE_KEY = 'sourcelens.answerCompletion.unreadSessions'
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

export function handleTerminalRun(options) {
  if (options.run?.status !== 'done' || !options.indicatorEnabled) {
    return { unreadChanged: false }
  }

  const isAnotherConversation =
    options.sessionUuid !== options.selectedSessionUuid
  if (!isAnotherConversation && !isInactive(options.documentRef)) {
    return { unreadChanged: false }
  }

  return {
    unreadChanged: markUnreadSession(
      options.storage,
      options.sessionUuid,
      options.run.uuid
    )
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
