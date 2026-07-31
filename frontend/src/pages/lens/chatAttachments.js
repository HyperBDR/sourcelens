export const MAX_ATTACHMENTS = 4
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024
export const MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
export const IMAGE_MIME = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
export const DOCUMENT_EXTENSIONS = ['.pdf', '.docx', '.pptx', '.xlsx']
export const ATTACHMENT_ACCEPT = [...IMAGE_MIME, ...DOCUMENT_EXTENSIONS].join(
  ','
)

export function classifyAttachment(file) {
  if (IMAGE_MIME.includes(file?.type || '')) {
    return 'image'
  }
  const name = String(file?.name || '').toLowerCase()
  if (DOCUMENT_EXTENSIONS.some((extension) => name.endsWith(extension))) {
    return 'document'
  }
  return ''
}

export function validateAttachment(file, options) {
  const kind = classifyAttachment(file)
  if (!kind) {
    return { kind: '', error: 'attachmentUnsupported' }
  }
  if ((options?.currentCount || 0) >= MAX_ATTACHMENTS) {
    return { kind, error: 'attachmentTooMany' }
  }
  if (kind === 'image') {
    if (!options?.acceptsImages) {
      return { kind, error: 'imageUnavailable' }
    }
    if ((file?.size || 0) > MAX_IMAGE_BYTES) {
      return { kind, error: 'imageTooLarge' }
    }
  }
  if (kind === 'document') {
    if (!options?.acceptsDocuments) {
      return { kind, error: 'documentUnavailable' }
    }
    if ((file?.size || 0) > MAX_DOCUMENT_BYTES) {
      return { kind, error: 'documentTooLarge' }
    }
  }
  return { kind, error: '' }
}

export function hasAttachmentErrorCode(error, code) {
  const pending = [error?.response?.data]
  while (pending.length) {
    const value = pending.pop()
    if (value === code) {
      return true
    }
    if (Array.isArray(value)) {
      pending.push(...value)
    } else if (value && typeof value === 'object') {
      pending.push(...Object.values(value))
    }
  }
  return false
}
