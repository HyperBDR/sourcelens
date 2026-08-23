const COST_STATUSES = new Set(['empty', 'unavailable', 'partial', 'priced'])

function nonNegativeNumber(value) {
  if (value === null || value === undefined || value === '') return null
  const number = Number(value)
  return Number.isFinite(number) && number >= 0 ? number : null
}

export function resolveCostPresentation(record = {}) {
  const explicitStatus = COST_STATUSES.has(record.cost_status)
    ? record.cost_status
    : null
  const totalCalls = nonNegativeNumber(
    record.total_calls ?? record.call_count ?? record.count
  )
  const totalCost = nonNegativeNumber(record.total_cost ?? record.cost)
  const pricedCalls = nonNegativeNumber(record.priced_calls)
  const unpricedCalls = nonNegativeNumber(record.unpriced_calls)

  if (explicitStatus) {
    return {
      status: explicitStatus,
      showAmount: explicitStatus !== 'unavailable',
      pricedCalls,
      unpricedCalls
    }
  }
  if (totalCalls === 0) {
    return {
      status: 'empty',
      showAmount: true,
      pricedCalls,
      unpricedCalls
    }
  }

  return {
    status: 'unknown',
    showAmount: totalCost !== null && totalCost > 0,
    pricedCalls,
    unpricedCalls
  }
}
