export function buildWorkspaceGuidePayload({ content }) {
  const normalizedContent = String(content || '').trim()

  return {
    enabled: Boolean(normalizedContent),
    content: normalizedContent
  }
}
