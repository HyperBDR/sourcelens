import assert from 'node:assert/strict'
import test from 'node:test'

import {
  messageMentionSegments,
  parseAssistantMentionToken,
  prependAssistantMentions,
  removeAssistantMentionToken
} from '../src/pages/lens/assistantMentions.js'

const assistants = [
  { uuid: 'assistant-hyperbdr', name: 'HyperBDR-AI-Assistant' },
  { uuid: 'assistant-company', name: 'Company-Knowledge-Base' }
]

test('recognizes an assistant mention token at the start of the draft', () => {
  assert.deepEqual(parseAssistantMentionToken('@Comp compare results'), {
    raw: '@Comp',
    query: 'Comp'
  })
  assert.equal(parseAssistantMentionToken('compare @Comp results'), null)
})

test('removes a completed mention token from the draft as one unit', () => {
  assert.equal(
    removeAssistantMentionToken('@Company-Knowledge-Base compare results'),
    'compare results'
  )
})

test('prepends every selected assistant with exactly one at-sign', () => {
  assert.equal(
    prependAssistantMentions('Compare the findings', [
      assistants[0],
      { ...assistants[1], name: '@Company-Knowledge-Base' }
    ]),
    '@HyperBDR-AI-Assistant @Company-Knowledge-Base Compare the findings'
  )
})

test('highlights every leading assistant mention in a sent message', () => {
  const segments = messageMentionSegments(
    '@HyperBDR-AI-Assistant @Company-Knowledge-Base Compare the findings',
    assistants
  )

  assert.deepEqual(
    segments
      .filter((segment) => segment.mentioned)
      .map((segment) => segment.text),
    ['@HyperBDR-AI-Assistant', '@Company-Knowledge-Base']
  )
})

test('highlights assistant names that contain spaces as one mention', () => {
  const segments = messageMentionSegments(
    '@Company Knowledge Compare the findings',
    [{ uuid: 'assistant-company', name: 'Company Knowledge' }]
  )

  assert.deepEqual(segments, [
    { text: '@Company Knowledge', mentioned: true },
    { text: ' ', mentioned: false },
    { text: 'Compare the findings', mentioned: false }
  ])
})
