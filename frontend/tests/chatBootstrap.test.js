import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const chatSource = () =>
  readFile(new URL('../src/pages/lens/Chat.vue', import.meta.url), 'utf8')

test('reveals loaded chat before waiting for active run recovery', async () => {
  const source = await chatSource()
  const messagesLoaded = source.indexOf('messages.value = loadedMessages')
  const resumeActiveRun = source.indexOf(
    'await maybeResumeActiveRun(session.uuid, isCurrentLoad)',
    messagesLoaded
  )
  const chatRevealed = source.indexOf('booted.value = true', messagesLoaded)

  assert.notEqual(messagesLoaded, -1)
  assert.notEqual(resumeActiveRun, -1)
  assert.ok(chatRevealed > messagesLoaded)
  assert.ok(chatRevealed < resumeActiveRun)
})

test('guards restored run state with the current session load', async () => {
  const source = await chatSource()

  assert.match(
    source,
    /await maybeResumeActiveRun\(session\.uuid, isCurrentLoad\)/
  )
  assert.match(
    source,
    /async function maybeResumeActiveRun\(sessionUuid, isCurrentLoad\)/
  )
})

test('selects a conversation when its route query changes', async () => {
  const source = await chatSource()
  const queryWatcher = source.indexOf('() => route.query.session')
  const sessionLookup = source.indexOf(
    'sessions.value.find((item) => item.uuid === sessionUuid)',
    queryWatcher
  )
  const selectWithoutRouteUpdate = source.indexOf(
    'void selectSession(session, false)',
    sessionLookup
  )

  assert.notEqual(queryWatcher, -1)
  assert.notEqual(sessionLookup, -1)
  assert.notEqual(selectWithoutRouteUpdate, -1)
})
