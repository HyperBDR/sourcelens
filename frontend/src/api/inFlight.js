/** Share concurrent requests for the same read-only resource. */
export function createInFlightRequestCache() {
  const pending = new Map()

  function run(key, load) {
    if (pending.has(key)) return pending.get(key)

    const request = Promise.resolve(load())
    pending.set(key, request)
    const clear = () => {
      if (pending.get(key) === request) pending.delete(key)
    }
    request.then(clear, clear)
    return request
  }

  return { run }
}
