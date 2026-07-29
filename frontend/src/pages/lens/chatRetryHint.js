export async function resolveRunStatus(getRun, runUuid) {
  try {
    return { resolved: true, run: await getRun(runUuid) }
  } catch {
    return { resolved: false, run: null }
  }
}

export function shouldShowRetryHint({
  isRunActive,
  messages,
  runStatusResolving
}) {
  if (runStatusResolving || isRunActive) return false
  const last = messages[messages.length - 1]
  return !!last && last.role === 'assistant' && !(last.content || '').trim()
}
