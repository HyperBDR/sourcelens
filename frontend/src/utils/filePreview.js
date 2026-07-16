// Helpers for deciding whether a delivered file can be previewed in the
// browser and, if so, how it should be rendered.

import api from '@/api'

export const PREVIEW_MAX_BYTES = 5 * 1024 * 1024

const IMAGE_EXTS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg']
const MARKDOWN_EXTS = ['md', 'markdown']
const TEXT_EXTS = [
  'txt',
  'csv',
  'json',
  'log',
  'yaml',
  'yml',
  'xml',
  'toml',
  'ini',
  'css',
  'sql',
  'js',
  'ts',
  'jsx',
  'tsx',
  'py',
  'java',
  'go',
  'rs',
  'c',
  'cpp',
  'h',
  'sh',
  'vue'
]

/**
 * Return the lowercase filename extension without the dot, or ''.
 */
export function extensionOf(filename) {
  const name = (filename || '').toLowerCase()
  const dot = name.lastIndexOf('.')
  return dot > -1 ? name.slice(dot + 1) : ''
}

/**
 * Fetch a delivered file's bytes through the authenticated API as a Blob.
 */
export async function fetchDeliverableBlob(file) {
  // api client baseURL already ends with /api; drop the leading prefix.
  const path = (file?.url || '').replace(/^\/api/, '')
  const response = await api.get(path, { responseType: 'blob' })
  return response.data
}

/**
 * Resolve how a file should be previewed.
 *
 * Returns one of 'image' | 'pdf' | 'html' | 'markdown' | 'text', or an
 * empty string when the file has no in-browser preview. Decides by
 * content_type first, then falls back to the filename extension.
 */
export function previewKind(file) {
  const type = (file?.content_type || '').toLowerCase()
  const ext = extensionOf(file?.filename)
  if (type.startsWith('image/') || IMAGE_EXTS.includes(ext)) {
    return 'image'
  }
  if (type === 'application/pdf' || ext === 'pdf') {
    return 'pdf'
  }
  if (type === 'text/html' || ext === 'html' || ext === 'htm') {
    return 'html'
  }
  if (type === 'text/markdown' || MARKDOWN_EXTS.includes(ext)) {
    return 'markdown'
  }
  if (
    type.startsWith('text/') ||
    type === 'application/json' ||
    TEXT_EXTS.includes(ext)
  ) {
    return 'text'
  }
  return ''
}

/**
 * Whether the file should offer an in-browser preview action. Files above
 * the size cap keep download-only to avoid stalling the browser.
 */
export function isPreviewable(file) {
  if (!file || !file.url) {
    return false
  }
  if (file.byte_size && file.byte_size > PREVIEW_MAX_BYTES) {
    return false
  }
  return Boolean(previewKind(file))
}
