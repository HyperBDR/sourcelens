import assert from 'node:assert/strict'
import test from 'node:test'

import { resolveChatViewport } from '../src/pages/lens/chatViewport.js'

test('leaves a full desktop visual viewport unconstrained', () => {
  assert.deepEqual(
    resolveChatViewport({
      layoutHeight: 1024,
      viewportHeight: 1024,
      viewportOffsetTop: 0,
      viewportScale: 1
    }),
    {
      constrained: false,
      height: 1024,
      offsetTop: 0
    }
  )
})

test('constrains an iPad landscape viewport reduced by browser chrome', () => {
  assert.deepEqual(
    resolveChatViewport({
      layoutHeight: 834,
      viewportHeight: 734,
      viewportOffsetTop: 0,
      viewportScale: 1
    }),
    {
      constrained: true,
      height: 734,
      offsetTop: 0
    }
  )
})

test('constrains an Android tablet viewport reduced by its keyboard', () => {
  assert.deepEqual(
    resolveChatViewport({
      layoutHeight: 800,
      viewportHeight: 480,
      viewportOffsetTop: 24,
      viewportScale: 1
    }),
    {
      constrained: true,
      height: 480,
      offsetTop: 24
    }
  )
})

test('ignores viewport reduction caused by pinch zoom', () => {
  assert.deepEqual(
    resolveChatViewport({
      layoutHeight: 834,
      viewportHeight: 556,
      viewportOffsetTop: 18,
      viewportScale: 1.5
    }),
    {
      constrained: false,
      height: 556,
      offsetTop: 18
    }
  )
})

test('returns no viewport constraint when the API is unavailable', () => {
  assert.deepEqual(
    resolveChatViewport({
      layoutHeight: 834,
      viewportHeight: undefined,
      viewportOffsetTop: undefined,
      viewportScale: undefined
    }),
    {
      constrained: false,
      height: null,
      offsetTop: 0
    }
  )
})
