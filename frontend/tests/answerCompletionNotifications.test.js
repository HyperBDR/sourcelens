import assert from 'node:assert/strict'
import test from 'node:test'

import {
  answerCompletionTitle,
  clearUnreadSession,
  handleTerminalRun,
  pollRunUntilTerminal,
  readUnreadSessions,
  requestNativeNotificationPermission,
  shouldReviewUnreadSession
} from '../src/utils/answerCompletionNotifications.js'

class MemoryStorage {
  constructor() {
    this.values = new Map()
  }

  getItem(key) {
    return this.values.get(key) ?? null
  }

  setItem(key, value) {
    this.values.set(key, String(value))
  }
}

function completionOptions(overrides = {}) {
  return {
    documentRef: {
      hasFocus: () => true,
      visibilityState: 'visible'
    },
    indicatorEnabled: true,
    run: { status: 'done', uuid: 'run-1' },
    selectedSessionUuid: 'session-b',
    sessionUuid: 'session-a',
    storage: new MemoryStorage(),
    ...overrides
  }
}

function createNotificationApi(permission = 'granted', requested = permission) {
  class NotificationApi {
    static instances = []

    static permission = permission

    static requestPermissionCalls = 0

    static async requestPermission() {
      NotificationApi.requestPermissionCalls += 1
      NotificationApi.permission = requested
      return requested
    }

    constructor(title, options) {
      this.title = title
      this.options = options
      this.closed = false
      NotificationApi.instances.push(this)
    }

    close() {
      this.closed = true
    }
  }

  return NotificationApi
}

test('uses a bell instead of an unread count in the browser title', () => {
  assert.equal(
    answerCompletionTitle({
      baseTitle: 'SourceLens',
      completionLabel: 'Answer completed',
      hasUnread: true
    }),
    '🔔 Answer completed · SourceLens'
  )
  assert.equal(
    answerCompletionTitle({
      baseTitle: 'SourceLens',
      completionLabel: 'Answer completed',
      hasUnread: false
    }),
    'SourceLens'
  )
})

test('reviews the selected unread conversation once the page is visible', () => {
  const unreadSessions = { 'session-a': 'run-1' }

  assert.equal(
    shouldReviewUnreadSession({
      documentRef: { visibilityState: 'visible' },
      selectedSessionUuid: 'session-a',
      unreadSessions
    }),
    true
  )
  assert.equal(
    shouldReviewUnreadSession({
      documentRef: { visibilityState: 'hidden' },
      selectedSessionUuid: 'session-a',
      unreadSessions
    }),
    false
  )
})

test('marks a completed non-selected conversation unread', () => {
  const options = completionOptions()

  const result = handleTerminalRun(options)

  assert.equal(result.unreadChanged, true)
  assert.deepEqual(readUnreadSessions(options.storage), {
    'session-a': 'run-1'
  })

  clearUnreadSession(options.storage, 'session-a')
  assert.deepEqual(readUnreadSessions(options.storage), {})
})

test('marks the selected conversation unread while its tab is inactive', () => {
  const options = completionOptions({
    documentRef: {
      hasFocus: () => false,
      visibilityState: 'hidden'
    },
    selectedSessionUuid: 'session-a'
  })

  const result = handleTerminalRun(options)

  assert.equal(result.unreadChanged, true)
})

test('does not mark the visible selected conversation unread', () => {
  const options = completionOptions({ selectedSessionUuid: 'session-a' })

  const result = handleTerminalRun(options)

  assert.equal(result.unreadChanged, false)
  assert.deepEqual(readUnreadSessions(options.storage), {})
})

test('does not mark a completion unread when reminders are disabled', () => {
  const options = completionOptions({ indicatorEnabled: false })

  const result = handleTerminalRun(options)

  assert.equal(result.unreadChanged, false)
  assert.deepEqual(readUnreadSessions(options.storage), {})
})

test('deduplicates replayed completion events by run uuid', () => {
  const options = completionOptions()

  const first = handleTerminalRun(options)
  const replay = handleTerminalRun(options)

  assert.equal(first.unreadChanged, true)
  assert.equal(replay.unreadChanged, false)
  assert.deepEqual(readUnreadSessions(options.storage), {
    'session-a': 'run-1'
  })
})

test('does not treat failed or cancelled runs as completed answers', () => {
  for (const status of ['failed', 'cancelled']) {
    const options = completionOptions({
      run: { status, uuid: `run-${status}` }
    })

    const result = handleTerminalRun(options)

    assert.deepEqual(result, {
      nativeNotificationShown: false,
      unreadChanged: false
    })
    assert.deepEqual(readUnreadSessions(options.storage), {})
  }
})

test('requests native notification permission only when it can prompt', async () => {
  const NotificationApi = createNotificationApi('default', 'granted')

  assert.equal(
    await requestNativeNotificationPermission(NotificationApi),
    'granted'
  )
  assert.equal(NotificationApi.requestPermissionCalls, 1)

  NotificationApi.permission = 'denied'
  assert.equal(
    await requestNativeNotificationPermission(NotificationApi),
    'denied'
  )
  assert.equal(NotificationApi.requestPermissionCalls, 1)
  assert.equal(await requestNativeNotificationPermission(undefined), null)
})

test('shows a native notification for an inactive completed run', () => {
  const NotificationApi = createNotificationApi()
  const storage = new MemoryStorage()
  let focused = 0
  let openedSession = ''
  const options = completionOptions({
    documentRef: {
      hasFocus: () => false,
      visibilityState: 'hidden'
    },
    indicatorEnabled: false,
    nativeNotification: {
      body: 'Your answer is ready.',
      enabled: true,
      NotificationRef: NotificationApi,
      onOpenConversation: (sessionUuid) => {
        openedSession = sessionUuid
      },
      title: 'Answer completed',
      windowRef: {
        focus: () => {
          focused += 1
        }
      }
    },
    selectedSessionUuid: 'session-a',
    storage
  })

  const result = handleTerminalRun(options)

  assert.deepEqual(result, {
    nativeNotificationShown: true,
    unreadChanged: false
  })
  assert.equal(NotificationApi.instances.length, 1)
  assert.deepEqual(NotificationApi.instances[0].options, {
    body: 'Your answer is ready.',
    renotify: false,
    tag: 'sourcelens-answer-run-1'
  })

  NotificationApi.instances[0].onclick()

  assert.equal(focused, 1)
  assert.equal(openedSession, 'session-a')
  assert.equal(NotificationApi.instances[0].closed, true)
})

test('does not show a native notification in the active tab', () => {
  const NotificationApi = createNotificationApi()
  const options = completionOptions({
    nativeNotification: {
      body: 'Your answer is ready.',
      enabled: true,
      NotificationRef: NotificationApi,
      title: 'Answer completed'
    }
  })

  const result = handleTerminalRun(options)

  assert.equal(result.nativeNotificationShown, false)
  assert.equal(NotificationApi.instances.length, 0)
})

test('deduplicates native notifications for replayed cross-tab events', () => {
  const NotificationApi = createNotificationApi()
  const storage = new MemoryStorage()
  const options = completionOptions({
    documentRef: {
      hasFocus: () => false,
      visibilityState: 'hidden'
    },
    nativeNotification: {
      body: 'Your answer is ready.',
      enabled: true,
      NotificationRef: NotificationApi,
      title: 'Answer completed'
    },
    storage
  })

  const first = handleTerminalRun(options)
  const replayFromAnotherTab = handleTerminalRun(options)

  assert.equal(first.nativeNotificationShown, true)
  assert.equal(replayFromAnotherTab.nativeNotificationShown, false)
  assert.equal(NotificationApi.instances.length, 1)
})

test('silently falls back when native notifications are unavailable', () => {
  const options = completionOptions({
    documentRef: {
      hasFocus: () => false,
      visibilityState: 'hidden'
    },
    nativeNotification: {
      body: 'Your answer is ready.',
      enabled: true,
      NotificationRef: undefined,
      title: 'Answer completed'
    }
  })

  assert.doesNotThrow(() => handleTerminalRun(options))
  assert.equal(handleTerminalRun(options).nativeNotificationShown, false)
  assert.deepEqual(readUnreadSessions(options.storage), {
    'session-a': 'run-1'
  })
})

test('polls server run state until it reaches a terminal status', async () => {
  const statuses = ['running', 'done']
  const requested = []
  let sleeps = 0

  const run = await pollRunUntilTerminal({
    getRun: async (runUuid) => {
      requested.push(runUuid)
      return { status: statuses.shift(), uuid: runUuid }
    },
    initialRun: { status: 'queued', uuid: 'run-1' },
    maxAttempts: 4,
    runUuid: 'run-1',
    sleep: async () => {
      sleeps += 1
    }
  })

  assert.equal(run.status, 'done')
  assert.deepEqual(requested, ['run-1', 'run-1'])
  assert.equal(sleeps, 2)
})

test('stops background polling without producing a terminal result', async () => {
  const run = await pollRunUntilTerminal({
    getRun: async () => {
      throw new Error('should not poll after cancellation')
    },
    initialRun: { status: 'queued', uuid: 'run-1' },
    isStopped: () => true,
    maxAttempts: 4,
    runUuid: 'run-1',
    sleep: async () => {}
  })

  assert.equal(run, null)
})
