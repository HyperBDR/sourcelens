const DEFAULT_FILENAME = 'SourceLens-conversation'

function cleanFilenamePart(value) {
  const printable = Array.from(String(value || ''), (character) => {
    const codePoint = character.codePointAt(0)
    return codePoint < 32 || codePoint === 127 ? ' ' : character
  }).join('')
  const normalized = printable
    .normalize('NFKC')
    .replace(/[<>:"/\\|?*%]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^[. ]+|[. ]+$/g, '')

  return Array.from(normalized).slice(0, 80).join('').trim()
}

export function buildQaPdfFilename({ summary = '', question = '' } = {}) {
  const name =
    cleanFilenamePart(summary) ||
    cleanFilenamePart(question) ||
    DEFAULT_FILENAME

  return `${name}.pdf`
}

export function filenameFromContentDisposition(value = '') {
  const encoded = value.match(/filename\*\s*=\s*utf-8''([^;]+)/i)
  let filename = ''
  if (encoded) {
    try {
      filename = decodeURIComponent(encoded[1].trim())
    } catch {
      filename = ''
    }
  }
  if (!filename) {
    const plain = value.match(/filename\s*=\s*(?:"([^"]+)"|([^;]+))/i)
    filename = plain?.[1] || plain?.[2]?.trim() || ''
  }
  const stem = filename.replace(/\.pdf$/i, '')
  const cleanStem = cleanFilenamePart(stem)
  return cleanStem ? `${cleanStem}.pdf` : ''
}

export function downloadQaPdf(response, { summary = '', question = '' } = {}) {
  const disposition = response?.headers?.['content-disposition'] || ''
  const filename =
    filenameFromContentDisposition(disposition) ||
    buildQaPdfFilename({ summary, question })
  const blob =
    response?.data instanceof Blob
      ? response.data
      : new Blob([response?.data || ''], { type: 'application/pdf' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.style.display = 'none'
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
