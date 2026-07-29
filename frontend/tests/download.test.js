import assert from 'node:assert/strict'
import test from 'node:test'

import { responseFilename } from '../src/utils/download.js'

test('responseFilename prefers and decodes RFC 5987 filenames', () => {
  const response = {
    headers: {
      'content-disposition':
        "attachment; filename=qa.pdf; filename*=UTF-8''AI%20Agent.pdf"
    }
  }

  assert.equal(responseFilename(response, 'fallback.pdf'), 'AI Agent.pdf')
})

test('responseFilename sanitizes path separators and uses a fallback', () => {
  assert.equal(
    responseFilename(
      {
        headers: {
          'content-disposition': 'attachment; filename="../answer.pdf"'
        }
      },
      'fallback.pdf'
    ),
    '.._answer.pdf'
  )
  assert.equal(responseFilename({}, 'fallback.pdf'), 'fallback.pdf')
})
