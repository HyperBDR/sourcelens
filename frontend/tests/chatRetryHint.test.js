import assert from 'node:assert/strict'
import test from 'node:test'

import { shouldShowRetryHint } from '../src/pages/lens/chatRetryHint.js'

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
