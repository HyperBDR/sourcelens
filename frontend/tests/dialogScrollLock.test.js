import assert from 'node:assert/strict'
import { afterEach, beforeEach, test } from 'node:test'

import {
  acquireBodyScrollLock,
  isTopDialog,
  registerDialog,
  unregisterDialog,
  releaseBodyScrollLock
} from '../src/components/ui/dialogScrollLock.js'

const originalDocument = globalThis.document

beforeEach(() => {
  globalThis.document = {
    body: {
      style: {
        overflow: 'auto'
      }
    }
  }
})

afterEach(() => {
  releaseBodyScrollLock()
  releaseBodyScrollLock()
  globalThis.document = originalDocument
})

test('keeps body scrolling locked until every dialog releases its lock', () => {
  acquireBodyScrollLock()
  acquireBodyScrollLock()

  releaseBodyScrollLock()
  assert.equal(document.body.style.overflow, 'hidden')

  releaseBodyScrollLock()
  assert.equal(document.body.style.overflow, 'auto')
})

test('ignores a release when no dialog acquired a lock', () => {
  releaseBodyScrollLock()

  assert.equal(document.body.style.overflow, 'auto')
})

test('only the topmost dialog handles global keyboard events', () => {
  const lowerDialog = Symbol('lower')
  const upperDialog = Symbol('upper')

  registerDialog(lowerDialog)
  registerDialog(upperDialog)

  assert.equal(isTopDialog(lowerDialog), false)
  assert.equal(isTopDialog(upperDialog), true)

  unregisterDialog(upperDialog)
  assert.equal(isTopDialog(lowerDialog), true)

  unregisterDialog(lowerDialog)
})
