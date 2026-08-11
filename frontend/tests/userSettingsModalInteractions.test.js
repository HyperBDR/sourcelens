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
    /min-h-11[\s\S]*?shrink-0[\s\S]*?rounded-lg[\s\S]*?px-3[\s\S]*?sm:min-h-0/
  )
})

test('User Settings uses a full-screen mobile panel with desktop constraints', () => {
  assert.match(
    modalSource,
    /settings-modal[\s\S]*?h-\[100dvh\][\s\S]*?max-h-none[\s\S]*?max-w-none[\s\S]*?flex-col[\s\S]*?rounded-none[\s\S]*?border-0/
  )
  assert.match(
    modalSource,
    /sm:h-\[526px\][\s\S]*?sm:max-h-\[82vh\][\s\S]*?sm:max-w-\[700px\][\s\S]*?sm:rounded-2xl[\s\S]*?sm:border/
  )
})

test('User Settings moves mobile sections into a horizontal scroll rail', () => {
  assert.match(
    modalSource,
    /settings-nav-tabs[\s\S]*?flex[\s\S]*?overflow-x-auto[\s\S]*?sm:block[\s\S]*?sm:overflow-visible/
  )
  assert.match(
    modalSource,
    /whitespace-nowrap[\s\S]*?sm:min-w-0[\s\S]*?sm:flex-1[\s\S]*?sm:truncate/
  )
  assert.match(
    modalSource,
    /\.settings-nav-scrollbar \{[\s\S]*?scrollbar-width: none;/
  )
  assert.match(
    modalSource,
    /\.settings-nav-scrollbar::-webkit-scrollbar \{[\s\S]*?display: none;/
  )
})

test('User Settings gives mobile content the full width and keeps desktop sidebar', () => {
  assert.match(
    modalSource,
    /settings-layout[\s\S]*?flex-col[\s\S]*?sm:flex-row/
  )
  assert.match(
    modalSource,
    /settings-nav[\s\S]*?w-full[\s\S]*?border-b[\s\S]*?sm:w-48[\s\S]*?sm:border-b-0[\s\S]*?sm:border-r/
  )
  assert.match(
    modalSource,
    /settings-content[\s\S]*?min-h-0[\s\S]*?flex-1[\s\S]*?overflow-y-auto/
  )
})

test('User Settings places logout in the mobile profile content', () => {
  assert.match(
    modalSource,
    /settings-mobile-logout[\s\S]*?sm:hidden[\s\S]*?@click="handleLogout"/
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
