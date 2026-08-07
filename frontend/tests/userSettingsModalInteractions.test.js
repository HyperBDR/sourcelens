import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const modalSource = readFileSync(
  new URL('../src/components/settings/UserSettingsModal.vue', import.meta.url),
  'utf8'
)
const selectSource = readFileSync(
  new URL('../src/components/ui/BaseSelect.vue', import.meta.url),
  'utf8'
)

test('BaseSelect stops Escape from bubbling while the listbox is open', () => {
  assert.match(
    selectSource,
    /if \(event\.key === 'Escape' && isOpen\.value\) \{[\s\S]*?event\.stopPropagation\(\)/
  )
})

test('User Settings exposes dialog semantics and focuses the close control', () => {
  assert.match(modalSource, /role="dialog"/)
  assert.match(modalSource, /aria-modal="true"/)
  assert.match(modalSource, /aria-labelledby="settings-modal-title"/)
  assert.match(modalSource, /id="settings-modal-title"/)
  assert.match(modalSource, /ref="closeButtonRef"/)
  assert.match(modalSource, /closeButtonRef\.value\?\.focus\(/)
})

test('User Settings closes from the visible backdrop click target', () => {
  assert.match(
    modalSource,
    /class="absolute inset-0 bg-black\/30 backdrop-blur-\[2px\]"[\s\S]*?@click="emit\('close'\)"/
  )
  assert.doesNotMatch(modalSource, /@click\.self="emit\('close'\)"/)
})

test('User Settings mobile navigation uses larger touch targets', () => {
  assert.match(
    modalSource,
    /min-h-11[\s\S]*?rounded-lg[\s\S]*?px-2\.5[\s\S]*?sm:min-h-0/
  )
})

test('User Settings navigation shows section labels on mobile', () => {
  assert.match(modalSource, /settings-nav flex w-36/)
  assert.doesNotMatch(
    modalSource,
    /class="hidden min-w-0 flex-1 truncate sm:block"/
  )
  assert.match(
    modalSource,
    /class="min-w-0 flex-1 truncate text-xs sm:text-sm"/
  )
})

test('User Settings profile fields stack labels above values', () => {
  assert.match(
    modalSource,
    /space-y-1 px-3 py-3[\s\S]*?text-xs font-medium text-theme-muted[\s\S]*?break-all text-sm font-medium leading-snug text-theme/
  )
  assert.doesNotMatch(
    modalSource,
    /flex items-center justify-between px-4 py-3/
  )
})

test('User Settings language selector does not add a second chevron', () => {
  const languageBlock = modalSource.match(
    /<!-- Language section -->[\s\S]*?<!-- Appearance section -->/
  )
  assert.ok(languageBlock, 'language section is present')
  assert.match(languageBlock[0], /<BaseSelect[\s\S]*?<\/BaseSelect>/)
  assert.doesNotMatch(
    languageBlock[0],
    /pointer-events-none absolute inset-y-0 right-3/
  )
})
