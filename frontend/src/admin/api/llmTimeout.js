export const DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS = 180

const MIN_LLM_ADMIN_REQUEST_TIMEOUT_MS = 90000
const LLM_REQUEST_TIMEOUT_MARGIN_MS = 10000

export function resolveLLMConfigTestTimeoutMs(body) {
  const configuredSeconds = Number(body?.config?.request_timeout_seconds)
  const effectiveSeconds =
    Number.isFinite(configuredSeconds) && configuredSeconds > 0
      ? configuredSeconds
      : DEFAULT_LLM_REQUEST_TIMEOUT_SECONDS

  return Math.max(
    MIN_LLM_ADMIN_REQUEST_TIMEOUT_MS,
    effectiveSeconds * 1000 + LLM_REQUEST_TIMEOUT_MARGIN_MS
  )
}
