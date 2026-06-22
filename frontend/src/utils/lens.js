/**
 * Build the public base URL for shareable links.
 *
 * Prefers the `public_base_url` GlobalSetting when it has been loaded
 * (e.g. in the admin console), otherwise falls back to the current
 * browser origin. Trailing slashes are stripped.
 */
export function publicBaseUrl(globalSettings = []) {
  const setting = Array.isArray(globalSettings)
    ? globalSettings.find((item) => item.key === 'public_base_url')
    : null
  const value =
    setting && typeof setting.value === 'string' ? setting.value : ''
  return (value || window.location.origin).replace(/\/+$/, '')
}

/** Build the public URL for a single shared Q&A. */
export function qaShareUrl(token, globalSettings = []) {
  return `${publicBaseUrl(globalSettings)}/lens/qa/${token}`
}

/** Build the public URL for an assistant's chat page. */
export function assistantChatUrl(slug, globalSettings = []) {
  return `${publicBaseUrl(globalSettings)}/lens/assistants/${slug}/chat`
}

/** Build the public URL for an assistant's shared Q&A list page. */
export function assistantQaListUrl(slug, globalSettings = []) {
  return `${publicBaseUrl(globalSettings)}/lens/assistants/${slug}/qa`
}
