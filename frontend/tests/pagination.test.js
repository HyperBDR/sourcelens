import assert from 'node:assert/strict'
import test from 'node:test'

import { collectPaginatedResults } from '../src/api/pagination.js'

test('collects every page from a paginated API response', async () => {
  const requestedPages = []
  const pages = {
    1: {
      count: 3,
      next: 'http://example.test/items/?page=2',
      results: [{ id: 1 }, { id: 2 }]
    },
    2: {
      count: 3,
      next: null,
      results: [{ id: 3 }]
    }
  }

  const results = await collectPaginatedResults(async (page) => {
    requestedPages.push(page)
    return pages[page]
  })

  assert.deepEqual(requestedPages, [1, 2])
  assert.deepEqual(
    results.map((item) => item.id),
    [1, 2, 3]
  )
})

test('accepts an unpaginated list response', async () => {
  const results = await collectPaginatedResults(async () => [{ id: 1 }])

  assert.deepEqual(results, [{ id: 1 }])
})
