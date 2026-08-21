import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { resolveCostPresentation } from '../src/admin/utils/llmCostPresentation.js'

test('unpriced calls do not render as a zero-dollar amount', () => {
  const presentation = resolveCostPresentation({
    total_calls: 144,
    total_cost: 0,
    priced_calls: 0,
    unpriced_calls: 144,
    cost_status: 'unavailable'
  })

  assert.equal(presentation.status, 'unavailable')
  assert.equal(presentation.showAmount, false)
  assert.equal(presentation.unpricedCalls, 144)
})

test('an explicitly priced zero remains a real zero-dollar amount', () => {
  const presentation = resolveCostPresentation({
    total_calls: 1,
    total_cost: 0,
    priced_calls: 1,
    unpriced_calls: 0,
    cost_status: 'priced'
  })

  assert.equal(presentation.status, 'priced')
  assert.equal(presentation.showAmount, true)
})

test('legacy zero-cost payloads are treated as unknown pricing coverage', () => {
  const presentation = resolveCostPresentation({
    total_calls: 144,
    total_cost: 0
  })

  assert.equal(presentation.status, 'unknown')
  assert.equal(presentation.showAmount, false)
})

test('partial pricing keeps the known amount and exposes missing calls', () => {
  const presentation = resolveCostPresentation({
    total_calls: 4,
    total_cost: 1.25,
    priced_calls: 3,
    unpriced_calls: 1,
    cost_status: 'partial'
  })

  assert.equal(presentation.status, 'partial')
  assert.equal(presentation.showAmount, true)
  assert.equal(presentation.unpricedCalls, 1)
})

test('LLM stats uses pricing coverage for totals, models, and charts', async () => {
  const contents = await readFile(
    new URL('../src/admin/pages/LLM/Stats.vue', import.meta.url),
    'utf8'
  )

  assert.match(contents, /summaryCostPresentation/)
  assert.match(contents, /costDisplayText\(row\)/)
  assert.match(contents, /costCoverageNote\(row\)/)
  assert.match(contents, /summaryCostPresentation\.value\.status === 'priced'/)
})
