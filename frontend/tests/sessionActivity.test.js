import assert from 'node:assert/strict'
import test from 'node:test'

import { createSessionActivityController } from '../src/utils/sessionActivityState.js'

function sessionActivity() {
  return createSessionActivityController({
    activities: {},
    notifications: [],
    unreadSessions: {}
  })
}

test('keeps a session active until every activity finishes', () => {
  const activity = sessionActivity()

  activity.beginActivity('session-a', 'run:1')
  activity.beginActivity('session-a', 'pdf:1')
  assert.equal(activity.hasActivity('session-a'), true)

  activity.endActivity('session-a', 'run:1')
  assert.equal(activity.hasActivity('session-a'), true)

  activity.endActivity('session-a', 'pdf:1')
  assert.equal(activity.hasActivity('session-a'), false)
})

test('stacks notifications and dismisses them independently', () => {
  const activity = sessionActivity()

  const first = activity.notify({ duration: 60_000, message: 'First' })
  const second = activity.notify({ duration: 60_000, message: 'Second' })
  assert.deepEqual(
    activity.state.notifications.map((item) => item.message),
    ['First', 'Second']
  )

  activity.dismissNotification(first)
  assert.deepEqual(
    activity.state.notifications.map((item) => item.message),
    ['Second']
  )

  activity.dismissNotification(second)
})
