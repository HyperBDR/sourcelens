import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const modalSource = readFileSync(
  new URL('../src/components/lens/FilePreviewModal.vue', import.meta.url),
  'utf8'
)

const styleMatch = modalSource.match(/<style scoped>([\s\S]*?)<\/style>/)

assert.ok(styleMatch, 'FilePreviewModal must define a scoped style block')

const styleSource = styleMatch[1]

const getCssBlock = (selector) => {
  const escapedSelector = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = styleSource.match(
    new RegExp(`${escapedSelector}\\s*\\{([^}]*)\\}`)
  )
  assert.ok(match, `Missing CSS block for ${selector}`)
  return match[1]
}

test('preview panel and body use theme surface tokens instead of light hex', () => {
  const panel = getCssBlock('.preview-panel')
  const body = getCssBlock('.preview-body')

  assert.match(panel, /background:\s*var\(--sl-bg-surface\)/)
  assert.match(body, /background:\s*var\(--sl-bg-canvas\)/)
  assert.doesNotMatch(panel, /background:\s*#fff\b/)
  assert.doesNotMatch(body, /background:\s*#f8fafc\b/)
})

test('preview text chrome follows theme foreground tokens', () => {
  const title = getCssBlock('.preview-title')
  const status = getCssBlock('.preview-status')
  const text = getCssBlock('.preview-text')

  assert.match(title, /color:\s*var\(--sl-text-primary\)/)
  assert.match(status, /color:\s*var\(--sl-text-muted\)/)
  assert.match(text, /color:\s*var\(--sl-text-primary\)/)
})

test('PPTX host mounts while the preview is loading', () => {
  const modalSource = readFileSync(
    new URL('../src/components/lens/FilePreviewModal.vue', import.meta.url),
    'utf8'
  )
  const pptxHostIndex = modalSource.indexOf('ref="pptxHost"')
  const loadingIndex = modalSource.indexOf('class="preview-status"')

  assert.ok(pptxHostIndex > -1, 'PPTX preview host must exist')
  assert.ok(loadingIndex > -1, 'preview loading state must exist')
  assert.ok(
    pptxHostIndex < loadingIndex,
    'PPTX host must be declared before the loading branch'
  )
  assert.match(
    modalSource.slice(pptxHostIndex - 120, pptxHostIndex + 80),
    /v-if="kind === 'pptx'"/
  )
})

test('PPTX preview recalculates its viewport after fullscreen changes', () => {
  assert.match(modalSource, /function getPptxPreviewSize\(\)/)
  assert.match(modalSource, /previewPanel\.value\.clientWidth/)
  assert.match(modalSource, /pptxHost\.value\.innerHTML = ''/)
  assert.match(modalSource, /function waitForPptxLayout\(\)/)
  assert.match(modalSource, /await renderPptx\(pptxBuffer, loadSeq\)/)
  assert.match(modalSource, /renderPptx\(pptxBuffer, loadSeq\)/)
})

test('PPTX keyboard navigation keeps Space from closing the preview', () => {
  assert.match(modalSource, /mode: 'slide'/)
  assert.match(modalSource, /event\.preventDefault\(\)/)
  assert.match(modalSource, /event\.key === 'ArrowLeft' \? -1 : 1/)
  assert.match(modalSource, /turnPptxPage\(direction\)/)
})

test('DOCX preview restores document typography and table layout', () => {
  assert.match(styleSource, /\.preview-docx :deep\(h1\)/)
  assert.match(styleSource, /\.preview-docx :deep\(p\)/)
  assert.match(styleSource, /\.preview-docx :deep\(table\)/)
  assert.match(styleSource, /\.preview-docx :deep\(li\)/)
})

test('DOCX preview uses the browser renderer for document styles', () => {
  assert.match(modalSource, /import\('docx-preview'\)/)
  assert.match(modalSource, /renderAsync\(blob, docxHost\.value/)
  assert.match(modalSource, /ref="docxHost"/)
  assert.doesNotMatch(modalSource, /mammoth\.convertToHtml/)
})
