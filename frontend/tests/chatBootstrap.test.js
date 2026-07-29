import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const chatSource = () =>
  readFile(new URL('../src/pages/lens/Chat.vue', import.meta.url), 'utf8')

test('reveals loaded chat before waiting for active run recovery', async () => {
  const source = await chatSource()
  const messagesLoaded = source.indexOf('messages.value = loadedMessages')
  const resumeActiveRun = source.indexOf(
    'await maybeResumeActiveRun(session.uuid)',
    messagesLoaded
  )
  const chatRevealed = source.indexOf('booted.value = true', messagesLoaded)

  assert.notEqual(messagesLoaded, -1)
  assert.notEqual(resumeActiveRun, -1)
  assert.ok(chatRevealed > messagesLoaded)
  assert.ok(chatRevealed < resumeActiveRun)
})
