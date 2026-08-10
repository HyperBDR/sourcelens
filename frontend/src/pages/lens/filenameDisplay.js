const DEFAULT_MAX_LENGTH = 22

export function compactFilename(filename, maxLength = DEFAULT_MAX_LENGTH) {
  const name = String(filename || '')
  if (name.length <= maxLength || maxLength < 7) return name

  const extensionIndex = name.lastIndexOf('.')
  const extension = extensionIndex > 0 ? name.slice(extensionIndex) : ''
  const ellipsis = '...'
  const available = maxLength - extension.length - ellipsis.length

  if (available < 2) {
    return `${ellipsis}${name.slice(-(maxLength - ellipsis.length))}`
  }

  const stem = extension ? name.slice(0, extensionIndex) : name
  const suffixMatch = stem.match(/(（[^（）]*）|\([^()]*\))$/)
  const preservedSuffix = suffixMatch?.[1] || ''

  if (preservedSuffix && preservedSuffix.length < available) {
    const prefixLength = available - preservedSuffix.length
    return `${stem.slice(0, prefixLength)}${ellipsis}${preservedSuffix}${extension}`
  }

  const prefixLength = Math.max(1, Math.ceil(available * 0.4))
  const suffixLength = available - prefixLength

  return `${stem.slice(0, prefixLength)}${ellipsis}${stem.slice(
    -suffixLength
  )}${extension}`
}
