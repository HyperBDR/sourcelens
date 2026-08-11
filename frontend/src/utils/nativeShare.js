/** Return whether the browser exposes the Web Share API. */
export function supportsNativeShare(target = globalThis.navigator) {
  return typeof target?.share === 'function'
}

/** Share content through the operating system and normalize the outcome. */
export async function shareWithNative(payload, target = globalThis.navigator) {
  if (!supportsNativeShare(target)) {
    return { status: 'unsupported' }
  }

  try {
    await target.share(payload)
    return { status: 'shared' }
  } catch (error) {
    if (error?.name === 'AbortError') {
      return { status: 'cancelled' }
    }
    return { error, status: 'failed' }
  }
}
