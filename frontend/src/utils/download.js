export function responseFilename(response, fallback = 'download') {
  const disposition = response?.headers?.['content-disposition'] || ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const plain = disposition.match(/filename="?([^";]+)"?/i)?.[1]
  let filename = fallback
  if (encoded) {
    try {
      filename = decodeURIComponent(encoded)
    } catch {
      filename = fallback
    }
  } else if (plain) {
    filename = plain
  }
  return filename.replace(/[\\/]/g, '_') || fallback
}

export function downloadResponseBlob(response, fallbackFilename) {
  const objectUrl = URL.createObjectURL(response.data)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = responseFilename(response, fallbackFilename)
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0)
}
