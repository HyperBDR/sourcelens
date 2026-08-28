export function isComposingKeyboardEvent(event) {
  return event.isComposing || event.keyCode === 229
}

export function resolveComposerEnterAction(event) {
  if (
    event.key !== 'Enter' ||
    isComposingKeyboardEvent(event) ||
    event.ctrlKey ||
    event.metaKey ||
    event.altKey
  ) {
    return null
  }

  return event.shiftKey ? 'newline' : 'primary'
}
