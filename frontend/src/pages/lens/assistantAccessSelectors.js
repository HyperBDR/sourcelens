export function assignmentFirstOptions(selectedIds, optionCache, pageOptions) {
  const selected = Array.isArray(selectedIds) ? selectedIds : []
  const page = Array.isArray(pageOptions) ? pageOptions : []
  const optionsById = new Map(optionCache)
  page.forEach((option) => optionsById.set(option.id, option))
  const selectedIdSet = new Set(selected)

  return [
    ...selected.map((id) => optionsById.get(id) || { id, name: `#${id}` }),
    ...page.filter((option) => !selectedIdSet.has(option.id))
  ]
}

export function appendUniqueOptions(currentOptions, nextOptions) {
  const options = Array.isArray(currentOptions) ? currentOptions : []
  const next = Array.isArray(nextOptions) ? nextOptions : []
  const seen = new Set(options.map((option) => option.id))

  return [
    ...options,
    ...next.filter((option) => {
      if (seen.has(option.id)) return false
      seen.add(option.id)
      return true
    })
  ]
}

export function createLatestRequestRunner() {
  let version = 0

  return {
    invalidate() {
      version += 1
    },
    async run(request) {
      const requestVersion = ++version
      try {
        const value = await request()
        return { current: requestVersion === version, value }
      } catch (error) {
        return { current: requestVersion === version, error }
      }
    }
  }
}
