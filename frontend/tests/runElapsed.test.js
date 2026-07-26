import assert from 'node:assert/strict'
import test from 'node:test'

import { activeRunElapsedSeconds } from '../src/utils/runElapsed.js'

const CREATED_AT = '2026-07-26T08:00:00.000Z'
const CREATED_AT_MS = Date.parse(CREATED_AT)

test('hydrates active run elapsed time from its creation time', () => {
  const elapsed = activeRunElapsedSeconds(
    { status: 'running', created_at: CREATED_AT },
    CREATED_AT_MS + 75000
  )

  assert.equal(elapsed, 75)
})

test('preserves the baseline across active status transitions', () => {
  for (const status of ['queued', 'running', 'streaming']) {
    const elapsed = activeRunElapsedSeconds(
      { status, created_at: CREATED_AT },
      CREATED_AT_MS + 75000
    )

    assert.equal(elapsed, 75)
  }
})

test('catches up after a delayed timer tick', () => {
  const run = { status: 'streaming', created_at: CREATED_AT }

  assert.equal(activeRunElapsedSeconds(run, CREATED_AT_MS + 1000), 1)
  assert.equal(activeRunElapsedSeconds(run, CREATED_AT_MS + 76000), 76)
})

test('returns zero for missing, invalid, or future creation times', () => {
  const now = CREATED_AT_MS

  assert.equal(activeRunElapsedSeconds({ status: 'running' }, now), 0)
  assert.equal(
    activeRunElapsedSeconds(
      { status: 'running', created_at: 'not-a-date' },
      now
    ),
    0
  )
  assert.equal(
    activeRunElapsedSeconds({ status: 'running', created_at: '0' }, now),
    0
  )
  assert.equal(
    activeRunElapsedSeconds(
      {
        status: 'running',
        created_at: '2026-07-26T08:00:01.000Z'
      },
      now
    ),
    0
  )
})

test('returns zero after a run reaches a terminal status', () => {
  const elapsed = activeRunElapsedSeconds(
    { status: 'done', created_at: CREATED_AT },
    CREATED_AT_MS + 75000
  )

  assert.equal(elapsed, 0)
})
