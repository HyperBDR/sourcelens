import assert from 'node:assert/strict'
import test from 'node:test'

import {
  appendUniqueOptions,
  assignmentFirstOptions,
  createLatestRequestRunner
} from '../src/pages/lens/assistantAccessSelectors.js'

test('appends new options once while preserving loaded order', () => {
  const options = appendUniqueOptions(
    [
      { id: 1, name: 'first' },
      { id: 2, name: 'second' }
    ],
    [
      { id: 2, name: 'duplicate' },
      { id: 3, name: 'third' }
    ]
  )

  assert.deepEqual(options, [
    { id: 1, name: 'first' },
    { id: 2, name: 'second' },
    { id: 3, name: 'third' }
  ])
})

test('pins every assignment before the current result page', () => {
  const cache = new Map([
    [101, { id: 101, username: 'outside-page' }],
    [2, { id: 2, username: 'selected-on-page' }]
  ])
  const page = [
    { id: 1, username: 'first-result' },
    { id: 2, username: 'selected-on-page' },
    { id: 3, username: 'last-result' }
  ]

  const options = assignmentFirstOptions([101, 2], cache, page)

  assert.deepEqual(
    options.map((option) => option.id),
    [101, 2, 1, 3]
  )
})

test('keeps selections stable when the result page changes', () => {
  const cache = new Map([
    [101, { id: 101, username: 'original-assignment' }],
    [8, { id: 8, username: 'selected-search-result' }]
  ])

  const options = assignmentFirstOptions([101, 8], cache, [
    { id: 22, username: 'different-page-result' }
  ])

  assert.deepEqual(
    options.map((option) => option.id),
    [101, 8, 22]
  )
})

test('falls back to a removable option when metadata is unavailable', () => {
  const options = assignmentFirstOptions([404], new Map(), [])

  assert.deepEqual(options, [{ id: 404, name: '#404' }])
})

test('marks an older request stale after a newer request starts', async () => {
  const runner = createLatestRequestRunner()
  let resolveFirst
  let resolveSecond
  const first = runner.run(
    () =>
      new Promise((resolve) => {
        resolveFirst = resolve
      })
  )
  const second = runner.run(
    () =>
      new Promise((resolve) => {
        resolveSecond = resolve
      })
  )

  resolveSecond('new results')
  resolveFirst('old results')

  assert.deepEqual(await second, { current: true, value: 'new results' })
  assert.deepEqual(await first, { current: false, value: 'old results' })
})
