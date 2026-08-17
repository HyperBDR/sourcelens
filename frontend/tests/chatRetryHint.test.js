import assert from 'node:assert/strict'
import test from 'node:test'

import {
  resolveRunStatus,
  shouldShowRetryHint
} from '../src/pages/lens/chatRetryHint.js'

const emptyAnswerMessages = [
  { role: 'user', content: 'What changed?' },
  { role: 'assistant', content: '' }
]

test('hides retry guidance while an active run status is unresolved', () => {
  assert.equal(
    shouldShowRetryHint({
      isRunActive: false,
      messages: emptyAnswerMessages,
      runStatusResolving: true
    }),
    false
  )

  assert.equal(
    shouldShowRetryHint({
      isRunActive: true,
      messages: emptyAnswerMessages,
      runStatusResolving: false
    }),
    false
  )
})

test('shows retry guidance after a failed empty-answer run is resolved', () => {
  assert.equal(
    shouldShowRetryHint({
      isRunActive: false,
      messages: emptyAnswerMessages,
      runStatusResolving: true
    }),
    false
  )

  assert.equal(
    shouldShowRetryHint({
      isRunActive: false,
      messages: emptyAnswerMessages,
      runStatusResolving: false
    }),
    true
  )
})

test('shows retry guidance after a terminal empty-answer run is resolved', () => {
  assert.equal(
    shouldShowRetryHint({
      isRunActive: false,
      messages: emptyAnswerMessages,
      runStatusResolving: true
    }),
    false
  )

  assert.equal(
    shouldShowRetryHint({
      isRunActive: false,
      messages: emptyAnswerMessages,
      runStatusResolving: false
    }),
    true
  )
})

test('does not show retry guidance when the last message has answer text', () => {
  assert.equal(
    shouldShowRetryHint({
      isRunActive: false,
      messages: [
        { role: 'user', content: 'What changed?' },
        { role: 'assistant', content: 'The run completed.' }
      ],
      runStatusResolving: false
    }),
    false
  )
})

test('does not show retry guidance for a pending clarification', () => {
  assert.equal(
    shouldShowRetryHint({
      isRunActive: false,
      messages: [
        { role: 'user', content: 'Analyze the deployment.' },
        {
          role: 'assistant',
          content: '',
          thinking: {
            status: 'awaiting_user_input',
            outcome: 'blocked',
            termination_detail: {
              reason: 'needs_user_input'
            }
          }
        }
      ],
      runStatusResolving: false
    }),
    false
  )
})

test('does not show retry guidance when runtime details explain an empty answer', () => {
  assert.equal(
    shouldShowRetryHint({
      isRunActive: false,
      messages: [
        { role: 'user', content: 'Analyze the deployment.' },
        {
          role: 'assistant',
          content: '',
          thinking: {
            status: 'done',
            outcome: 'blocked',
            termination_detail: {
              reason: 'evidence_unavailable'
            }
          }
        }
      ],
      runStatusResolving: false
    }),
    false
  )
})

test('keeps retry guidance hidden when run status cannot be loaded', async () => {
  const resolution = await resolveRunStatus(async () => {
    throw new Error('temporary network failure')
  }, 'run-uuid')

  assert.deepEqual(resolution, { resolved: false, run: null })
  assert.equal(
    shouldShowRetryHint({
      isRunActive: false,
      messages: emptyAnswerMessages,
      runStatusResolving: !resolution.resolved
    }),
    false
  )
})

test('returns the resolved run when its status loads', async () => {
  const run = { uuid: 'run-uuid', status: 'running' }

  assert.deepEqual(await resolveRunStatus(async () => run, run.uuid), {
    resolved: true,
    run
  })
})
