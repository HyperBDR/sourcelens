export async function collectPaginatedResults(fetchPage) {
  const items = []
  let page = 1
  let hasMore = true

  while (hasMore) {
    const payload = await fetchPage(page)
    if (Array.isArray(payload)) {
      return items.concat(payload)
    }

    const results = Array.isArray(payload?.results) ? payload.results : []
    items.push(...results)

    const count = Number(payload?.count)
    const hasMoreByCount = Number.isFinite(count) && items.length < count
    hasMore = Boolean(payload?.next) || hasMoreByCount
    if (!hasMore || results.length === 0) {
      return items
    }

    page += 1
  }

  return items
}
