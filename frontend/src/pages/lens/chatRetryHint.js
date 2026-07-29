export function shouldShowRetryHint({
  isRunActive,
  messages,
  runStatusResolving
}) {
  if (runStatusResolving || isRunActive) return false
  const last = messages[messages.length - 1]
  return !!last && last.role === 'assistant' && !(last.content || '').trim()
}
