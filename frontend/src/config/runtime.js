const parseBoolean = (value) => {
  if (typeof value === 'boolean') return value
  if (typeof value !== 'string') return undefined
  return value.toLowerCase() === 'true'
}

export const getTurnstileConfig = (buildSiteKey = '') => {
  const runtime = globalThis.__SOURCELENS_CONFIG__ || {}
  const siteKey = runtime.turnstileSiteKey ?? buildSiteKey ?? ''
  const runtimeEnabled = parseBoolean(runtime.turnstileEnabled)

  return {
    enabled: runtimeEnabled ?? Boolean(siteKey),
    siteKey
  }
}
