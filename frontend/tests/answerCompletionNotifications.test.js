import assert from 'node:assert/strict'
import test from 'node:test'

import {
  browserNotificationState,
  clearUnreadSession,
  enableBrowserNotifications,
  handleTerminalRun,
  readUnreadSessions
} from '../src/utils/answerCompletionNotifications.js'

class MemoryStorage {
  constructor() {
    this.values = new Map()
  }

  getItem(key) {
    return this.values.get(key) ?? null
  }

  removeItem(key) {
    this.values.delete(key)
  }

  setItem(key, value) {
    this.values.set(key, String(value))
  }
}

class FakeNotification {
  static permission = 'granted'
  static created = []

  constructor(title, options) {
    this.title = title
    this.options = options
    this.closed = false
    FakeNotification.created.push(this)
  }

  close() {
    this.closed = true
  }
}

function completionOptions(overrides = {}) {
  const storage = overrides.storage || new MemoryStorage()
  return {
    browserEnabled: true,
    documentRef: {
      hasFocus: () => false,
      visibilityState: 'hidden'
    },
    icon: '/icons/notification-bell.svg',
    indicatorEnabled: true,
    isSecureContext: true,
    notificationApi: FakeNotification,
    onOpen: () => {},
    run: { status: 'done', uuid: 'run-1' },
    selectedSessionUuid: 'session-b',
    sessionUuid: 'session-a',
    storage,
    title: 'Answer completed',
    ...overrides
  }
}

test('represents unsupported, blocked, disabled, and enabled states', () => {
  assert.equal(
    browserNotificationState({
      enabled: false,
      isSecureContext: false,
      notificationApi: FakeNotification
    }),
    'unsupported'
  )

  FakeNotification.permission = 'denied'
  assert.equal(
    browserNotificationState({
      enabled: false,
      isSecureContext: true,
      notificationApi: FakeNotification
    }),
    'blocked'
  )

  FakeNotification.permission = 'granted'
  assert.equal(
    browserNotificationState({
      enabled: false,
      isSecureContext: true,
      notificationApi: FakeNotification
    }),
    'disabled'
  )
  assert.equal(
    browserNotificationState({
      enabled: true,
      isSecureContext: true,
      notificationApi: FakeNotification
    }),
    'enabled'
  )
})

test('requests browser permission only from an explicit enable action', async () => {
  let requests = 0
  const notificationApi = {
    permission: 'default',
    async requestPermission() {
      requests += 1
      this.permission = 'granted'
      return this.permission
    }
  }

  const state = await enableBrowserNotifications({
    isSecureContext: true,
    notificationApi
  })

  assert.equal(state, 'enabled')
  assert.equal(requests, 1)
})

test('does not repeat a permission prompt after the browser blocks it', async () => {
  let requests = 0
  const notificationApi = {
    permission: 'denied',
    async requestPermission() {
      requests += 1
      return this.permission
    }
  }

  const state = await enableBrowserNotifications({
    isSecureContext: true,
    notificationApi
  })

  assert.equal(state, 'blocked')
  assert.equal(requests, 0)
})

test('marks a completed background conversation unread', async () => {
  const options = completionOptions({ browserEnabled: false })

  const result = await handleTerminalRun(options)

  assert.equal(result.unreadChanged, true)
  assert.deepEqual(readUnreadSessions(options.storage), {
    'session-a': 'run-1'
  })

  clearUnreadSession(options.storage, 'session-a')
  assert.deepEqual(readUnreadSessions(options.storage), {})
})

test('does not mark the selected conversation unread', async () => {
  const options = completionOptions({
    browserEnabled: false,
    selectedSessionUuid: 'session-a'
  })

  const result = await handleTerminalRun(options)

  assert.equal(result.unreadChanged, false)
  assert.deepEqual(readUnreadSessions(options.storage), {})
})

test('does not treat failed or cancelled runs as completed answers', async () => {
  for (const status of ['failed', 'cancelled']) {
    const options = completionOptions({
      run: { status, uuid: `run-${status}` }
    })

    const result = await handleTerminalRun(options)

    assert.deepEqual(result, {
      browserNotified: false,
      unreadChanged: false
    })
    assert.deepEqual(readUnreadSessions(options.storage), {})
  }
})

test('sends one generic browser notification for an inactive tab', async () => {
  FakeNotification.created = []
  FakeNotification.permission = 'granted'
  const storage = new MemoryStorage()
  let focused = 0
  let opened = 0
  const options = completionOptions({
    onOpen: () => {
      focused += 1
      opened += 1
    },
    storage
  })

  const first = await handleTerminalRun(options)
  const replay = await handleTerminalRun(options)

  assert.equal(first.browserNotified, true)
  assert.equal(replay.browserNotified, false)
  assert.equal(FakeNotification.created.length, 1)
  assert.equal(FakeNotification.created[0].title, 'Answer completed')
  assert.deepEqual(FakeNotification.created[0].options, {
    icon: '/icons/notification-bell.svg',
    tag: 'sourcelens-answer-run-1'
  })

  FakeNotification.created[0].onclick()
  assert.equal(focused, 1)
  assert.equal(opened, 1)
  assert.equal(FakeNotification.created[0].closed, true)
})

test('does not send a browser notification while the tab is active', async () => {
  FakeNotification.created = []
  FakeNotification.permission = 'granted'
  const options = completionOptions({
    documentRef: {
      hasFocus: () => true,
      visibilityState: 'visible'
    }
  })

  const result = await handleTerminalRun(options)

  assert.equal(result.browserNotified, false)
  assert.equal(FakeNotification.created.length, 0)
})
