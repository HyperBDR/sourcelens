import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const readSource = (path) =>
  readFile(new URL(`../${path}`, import.meta.url), 'utf8')

test('keeps native browser notifications as a separate opt-in preference', async () => {
  const source = await readSource('src/store/preferences.js')

  assert.match(source, /nativeBrowserNotifications: false/)
  assert.match(source, /setNativeBrowserNotifications\(enabled\)/)
  assert.match(source, /savedNativeNotifications === 'true'/)
})

test('requests permission from the native notification switch click', async () => {
  const source = await readSource(
    'src/components/settings/AnswerNotificationSettings.vue'
  )

  assert.match(source, /@click="toggleNativeBrowserNotifications"/)
  assert.match(
    source,
    /requestNativeNotificationPermission\s*\(\s*window\.Notification\s*\)/
  )
})

test('uses one route-aware target for native and in-app completion clicks', async () => {
  const source = await readSource('src/pages/lens/Chat.vue')

  assert.match(source, /const navigationTarget = {/)
  assert.match(source, /params: { slug: assistantSlug }/)
  assert.match(source, /query: { session: sessionUuid }/)
  assert.match(
    source,
    /onOpenConversation: \(\) => router\.push\(navigationTarget\)/
  )
  assert.match(source, /to: navigationTarget/)
})

test('synchronizes completion preferences and unread state across tabs', async () => {
  const source = await readSource('src/pages/lens/Chat.vue')

  assert.match(source, /function handleCompletionStorage\(event\)/)
  assert.match(
    source,
    /window\.addEventListener\('storage', handleCompletionStorage\)/
  )
  assert.match(
    source,
    /window\.removeEventListener\('storage', handleCompletionStorage\)/
  )
})

test('provides English and Simplified Chinese native notification text', async () => {
  const [english, chinese] = await Promise.all([
    readSource('src/locales/en.json'),
    readSource('src/locales/zh-CN.json')
  ])
  const en = JSON.parse(english).settings.modal
  const zh = JSON.parse(chinese).settings.modal

  for (const messages of [en, zh]) {
    assert.ok(messages.nativeBrowserNotifications)
    assert.ok(messages.nativeBrowserNotificationsDesc)
    assert.ok(messages.nativeAnswerCompletedTitle)
    assert.ok(messages.nativeAnswerCompletedBody)
  }
})
