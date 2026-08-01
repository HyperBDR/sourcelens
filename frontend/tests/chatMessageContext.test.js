import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  precedingUserMessage,
  retryRunUuid,
  retryableUserMessage
} from '../src/pages/lens/chatMessageContext.js'

test('passes the clicked assistant reply to the retry handler', async () => {
  const chat = await readFile(
    new URL('../src/pages/lens/Chat.vue', import.meta.url),
    'utf8'
  )

  assert.match(chat, /@click="retryLastQuestion\(message\)"/)
})

test('keeps empty-answer Retry clicks from becoming a message', async () => {
  const chat = await readFile(
    new URL('../src/pages/lens/Chat.vue', import.meta.url),
    'utf8'
  )

  assert.match(chat, /@click="retryLastQuestion\(\)"/)
})

test('finds the user question for a historical assistant reply', () => {
  const messages = [
    { uuid: 'question-1', role: 'user', content: 'First question' },
    { uuid: 'answer-1', role: 'assistant', content: 'First answer' },
    { uuid: 'question-2', role: 'user', content: 'Second question' },
    { uuid: 'answer-2', role: 'assistant', content: 'Second answer' }
  ]

  const question = precedingUserMessage(messages, messages[1])

  assert.equal(question?.uuid, 'question-1')
})

test('returns null when the target reply is not in the message list', () => {
  const messages = [
    { uuid: 'question-1', role: 'user', content: 'First question' }
  ]

  const question = precedingUserMessage(messages, {
    uuid: 'missing-answer',
    role: 'assistant'
  })

  assert.equal(question, null)
})

test('finds the Run for a historical assistant reply', () => {
  const messages = [
    { uuid: 'question-1', role: 'user', content: 'First', run: 'run-1' },
    { uuid: 'answer-1', role: 'assistant', content: 'Answer', run: 'run-1' },
    { uuid: 'question-2', role: 'user', content: 'Second', run: 'run-2' },
    { uuid: 'answer-2', role: 'assistant', content: 'Answer', run: 'run-2' }
  ]

  assert.equal(retryRunUuid(messages, messages[1]), 'run-1')
})

test('uses the latest user Run for an empty-answer Retry hint', () => {
  const messages = [
    { uuid: 'question-1', role: 'user', content: 'First', run: 'run-1' },
    { uuid: 'answer-1', role: 'assistant', content: 'Answer', run: 'run-1' },
    { uuid: 'question-2', role: 'user', content: 'Second', run: 'run-2' }
  ]

  assert.equal(retryRunUuid(messages), 'run-2')
})

test('does not retry an attachment-only question without reusable files', () => {
  const messages = [
    {
      uuid: 'question-1',
      role: 'user',
      content: '',
      attachments: [{ uuid: 'document-1', kind: 'document' }]
    },
    { uuid: 'answer-1', role: 'assistant', content: '' }
  ]

  assert.equal(retryableUserMessage(messages, messages[1]), null)
  assert.equal(retryableUserMessage(messages), null)
})

test('does not retry text when its document cannot be replayed', () => {
  const messages = [
    {
      uuid: 'question-1',
      role: 'user',
      content: 'Validate this PDF',
      attachments: [{ uuid: 'document-1', kind: 'document' }]
    },
    { uuid: 'answer-1', role: 'assistant', content: '' }
  ]

  assert.equal(retryableUserMessage(messages, messages[1]), null)
  assert.equal(retryableUserMessage(messages), null)
})

test('keeps text questions retryable', () => {
  const messages = [
    { uuid: 'question-1', role: 'user', content: 'Try again' },
    { uuid: 'answer-1', role: 'assistant', content: '' }
  ]

  assert.equal(retryableUserMessage(messages, messages[1])?.uuid, 'question-1')
})
