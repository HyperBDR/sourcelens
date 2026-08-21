export function hasStatisticsData(total) {
  const value = Number(total)
  return Number.isFinite(value) && value > 0
}
