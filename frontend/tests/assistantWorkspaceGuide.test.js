import assert from 'node:assert/strict'
import test from 'node:test'

import { buildWorkspaceGuidePayload } from '../src/pages/lens/assistantWorkspaceGuide.js'

test('keeps a workspace guide enabled for general chat assistants', () => {
  const payload = buildWorkspaceGuidePayload({
    content: 'Use the engineering workspace guide.',
    selectedTask: 'general_chat'
  })

  assert.deepEqual(payload, {
    enabled: true,
    content: 'Use the engineering workspace guide.'
  })
})
