import assert from 'node:assert/strict'
import test from 'node:test'

import {
  clearUnreadSession,
  handleTerminalRun,
  pollRunUntilTerminal,
  readUnreadSessions
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

    assert.deepEqual(result, { unreadChanged: false })
    assert.deepEqual(readUnreadSessions(options.storage), {})
  }
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
