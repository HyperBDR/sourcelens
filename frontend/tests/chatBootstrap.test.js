import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const chatSource = () =>
  readFile(new URL('../src/pages/lens/Chat.vue', import.meta.url), 'utf8')

const assistantSwitcherSource = () =>
  readFile(
    new URL('../src/components/lens/AssistantSwitcher.vue', import.meta.url),
    'utf8'
  )

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

test('reviews a selected unread chat before active run recovery', async () => {
  const source = await chatSource()
  const selectSession = source.indexOf('async function selectSession(')
  const resumeActiveRun = source.indexOf(
    'await maybeResumeActiveRun(session.uuid, isCurrentLoad)',
    selectSession
  )
  const clearUnread = source.indexOf(
    'clearUnreadSession(window.localStorage, session.uuid)',
    selectSession
  )

  assert.notEqual(selectSession, -1)
  assert.notEqual(resumeActiveRun, -1)
  assert.notEqual(clearUnread, -1)
  assert.ok(clearUnread < resumeActiveRun)
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

test('switches assistants through the assistant chat route', async () => {
  const source = await assistantSwitcherSource()

  assert.match(
    source,
    /await router\.push\(`\/lens\/assistants\/\$\{slug\}\/chat`\)/
  )
})

test('loads sessions after selecting the route assistant', async () => {
  const source = await chatSource()
  const selectAssistant = source.indexOf(
    'selectedAssistantUuid.value = current.uuid'
  )
  const loadSessions = source.indexOf('await loadSessions()', selectAssistant)

  assert.notEqual(selectAssistant, -1)
  assert.notEqual(loadSessions, -1)
  assert.ok(loadSessions > selectAssistant)
})
