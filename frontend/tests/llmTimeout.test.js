import assert from 'node:assert/strict'
import test from 'node:test'

import {
  DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS,
  resolveLLMConfigTestTimeoutMs
} from '../src/admin/api/llmTimeout.js'

test('allows a configured timeout above 90 seconds with transport margin', () => {
  const timeout = resolveLLMConfigTestTimeoutMs({
    config: { request_timeout_seconds: 120 }
  })

  assert.equal(timeout, 130000)
})

test('uses the 180-second backend default when timeout is unset', () => {
  const timeout = resolveLLMConfigTestTimeoutMs({ config: {} })

  assert.equal(timeout, DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS * 1000 + 10000)
})

test('keeps the existing 90-second floor for shorter timeouts', () => {
  const timeout = resolveLLMConfigTestTimeoutMs({
    config: { request_timeout_seconds: 30 }
  })

  assert.equal(timeout, 90000)
})
