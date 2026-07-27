import assert from 'node:assert/strict'
import test from 'node:test'

import {
  credentialUrl,
  credentialUrlLabel,
  filterAndSortCredentials,
  formatCredentialDateTime
} from '../src/pages/lens/credentialHelpers.js'

const rows = [
  {
    name: 'GitHub organization',
    provider: 'github',
    auth_type: 'https_token',
    scope_summary: {
      organization_url: 'https://github.com/HyperBDR'
    },
    validation_status: 'success',
    validated_at: '2026-07-25T07:00:00Z',
    last_used_at: '2026-07-25T08:00:00Z'
  },
  {
    name: 'Feishu presentations',
    provider: 'feishu',
    auth_type: 'feishu_app',
    scope_summary: {
      folder_url:
        'https://oneprocloud.feishu.cn/drive/folder/folder-token?from=space'
    },
    validation_status: 'failed',
    validated_at: '2026-07-24T07:00:00Z',
    last_used_at: null
  }
]

test('filters credentials by query, provider, and validation status', () => {
  const result = filterAndSortCredentials(rows, {
    query: 'presentation',
    provider: 'feishu',
    validationStatus: 'failed'
  })

  assert.deepEqual(
    result.map((row) => row.name),
    ['Feishu presentations']
  )
})

test('treats a blank validation status as unchecked', () => {
  const result = filterAndSortCredentials(
    [
      {
        name: 'New credential',
        validation_status: ''
      }
    ],
    { validationStatus: 'unchecked' }
  )

  assert.deepEqual(
    result.map((row) => row.name),
    ['New credential']
  )
})

test('sorts credentials by most recently used first', () => {
  const result = filterAndSortCredentials(rows, {
    sort: 'last_used_desc'
  })

  assert.deepEqual(
    result.map((row) => row.name),
    ['GitHub organization', 'Feishu presentations']
  )
})

test('builds a compact URL label without query parameters', () => {
  assert.equal(
    credentialUrlLabel(rows[1]),
    'oneprocloud.feishu.cn/…/folder-token'
  )
  assert.equal(credentialUrl(rows[1]), rows[1].scope_summary.folder_url)
})

test('formats a complete timestamp with year and timezone', () => {
  const formatted = formatCredentialDateTime(
    '2026-07-25T07:00:00Z',
    'en',
    'UTC'
  )

  assert.match(formatted, /2026/)
  assert.match(formatted, /UTC/)
})
