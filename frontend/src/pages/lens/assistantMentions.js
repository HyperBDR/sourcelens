function normalizedAssistantName(name) {
  return String(name || '')
    .trim()
    .replace(/^@+/, '')
}

export function parseAssistantMentionToken(question) {
  const match = /^@([^\s]*)/.exec(String(question || ''))
  if (!match) return null
  return { raw: match[0], query: match[1] }
}

export function removeAssistantMentionToken(question) {
  const text = String(question || '')
  const token = parseAssistantMentionToken(text)
  if (!token) return text
  return text.slice(token.raw.length).trimStart()
}

export function prependAssistantMentions(question, assistants) {
  const mentions = assistants
    .map((assistant) => normalizedAssistantName(assistant.name))
    .filter(Boolean)
    .map((name) => `@${name}`)
    .join(' ')
  const content = String(question || '').trimStart()
  return [mentions, content].filter(Boolean).join(' ')
}

export function messageMentionSegments(content, assistants) {
  let remaining = String(content || '')
  const names = assistants
    .map((assistant) => normalizedAssistantName(assistant.name))
    .filter(Boolean)
    .sort((left, right) => right.length - left.length)
  const segments = []

  while (remaining.startsWith('@')) {
    const name = names.find(
      (candidate) =>
        remaining.startsWith(`@${candidate}`) &&
        (remaining.length === candidate.length + 1 ||
          /\s/.test(remaining[candidate.length + 1]))
    )
    if (!name) break
    const mention = `@${name}`
    segments.push({ text: mention, mentioned: true })
    remaining = remaining.slice(mention.length)
    const spacing = /^\s+/.exec(remaining)?.[0] || ''
    if (spacing) {
      segments.push({ text: spacing, mentioned: false })
      remaining = remaining.slice(spacing.length)
    }
  }

  if (remaining || !segments.length) {
    segments.push({ text: remaining, mentioned: false })
  }
  return segments
}
