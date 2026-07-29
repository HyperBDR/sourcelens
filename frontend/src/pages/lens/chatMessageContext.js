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
