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
