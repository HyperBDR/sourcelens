const ACTIVE_RUN_STATUSES = new Set(['queued', 'running', 'streaming'])
const ISO_DATE_TIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/
const ISO_TIME_ZONE = /(?:Z|[+-]\d{2}:\d{2})$/

export function activeRunElapsedSeconds(run, now = Date.now()) {
  if (!ACTIVE_RUN_STATUSES.has(run?.status)) {
    return 0
  }

  const createdAtValue = run?.created_at
  if (
    typeof createdAtValue !== 'string' ||
    !ISO_DATE_TIME.test(createdAtValue) ||
    !ISO_TIME_ZONE.test(createdAtValue)
  ) {
    return 0
  }

  const createdAt = Date.parse(createdAtValue)
  if (!Number.isFinite(createdAt) || createdAt > now) {
    return 0
  }

  return Math.floor((now - createdAt) / 1000)
}
