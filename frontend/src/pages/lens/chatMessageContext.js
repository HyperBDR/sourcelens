export function precedingUserMessage(messages, targetMessage) {
  const targetIndex = messages.findIndex(
    (message) => message.uuid === targetMessage?.uuid
  )
  if (targetIndex === -1) {
    return null
  }

  for (let index = targetIndex - 1; index >= 0; index -= 1) {
    if (messages[index].role === 'user') {
      return messages[index]
    }
  }
  return null
}

export function retryRunUuid(messages, targetMessage = null) {
  const userMessage = targetMessage
    ? precedingUserMessage(messages, targetMessage)
    : [...messages].reverse().find((message) => message.role === 'user')
  return targetMessage?.run || userMessage?.run || ''
}
