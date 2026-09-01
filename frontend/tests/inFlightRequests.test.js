import assert from 'node:assert/strict'
import test from 'node:test'

import { createInFlightRequestCache } from '../src/api/inFlight.js'

test('shares one in-flight request for the same assistant-list key', async () => {
  const cache = createInFlightRequestCache()
  let calls = 0
  let resolveRequest
  const load = () => {
    calls += 1
    return new Promise((resolve) => {
      resolveRequest = resolve
    })
  }

  const first = cache.run('active', load)
  const second = cache.run('active', load)
  resolveRequest(['assistant-1'])

  assert.equal(calls, 1)
  assert.deepEqual(await first, ['assistant-1'])
  assert.deepEqual(await second, ['assistant-1'])
})

test('does not share requests with different list filters', async () => {
  const cache = createInFlightRequestCache()
  let calls = 0

  await Promise.all([
    cache.run('active', async () => ++calls),
    cache.run('archived', async () => ++calls)
  ])

  assert.equal(calls, 2)
})

test('clears a failed request so the next load can retry', async () => {
  const cache = createInFlightRequestCache()
  const failure = new Error('temporary failure')

  await assert.rejects(
    cache.run('active', async () => {
      throw failure
    }),
    failure
  )

  assert.deepEqual(await cache.run('active', async () => ['assistant-1']), [
    'assistant-1'
  ])
})
