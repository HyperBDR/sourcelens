import assert from 'node:assert/strict'
import test from 'node:test'

import { lensNodeErrorMessage } from '../src/utils/lensNodeErrors.js'

test('maps an unavailable LensNode to the offline retry message', () => {
  const seen = []
  const message = lensNodeErrorMessage('LENSNODE_UNAVAILABLE', (key) => {
    seen.push(key)
    return key
  })

  assert.equal(message, 'lensNodeErrors.offline')
  assert.deepEqual(seen, ['lensNodeErrors.offline'])
})
