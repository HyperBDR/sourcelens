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

const userDockSource = () =>
  readFile(
    new URL('../src/components/lens/UserDock.vue', import.meta.url),
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

test('marks assistant filtering as search without autofill', async () => {
  const source = await assistantSwitcherSource()

  assert.match(
    source,
    /v-model="query"\s+type="search"\s+name="assistant-search"\s+autocomplete="off"/
  )
  assert.match(source, /inputmode="search"/)
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

test('shows an assistant welcome state on mobile before the first message', async () => {
  const source = await chatSource()

  assert.match(
    source,
    /v-if="\s*isMobile && !decoratedMessages\.length && !showLiveAnswer\s*"\s+class="chat-welcome"/
  )
  assert.match(source, /<h1 class="chat-welcome-title">/)
  assert.match(source, /\{\{ assistantName \}\}/)
  assert.match(source, /v-for="suggestion in promptSuggestions"/)
  assert.match(source, /@click="applyPromptSuggestion\(suggestion\)"/)
  assert.match(source, /'composer-wrap-empty': isEmptyConversation/)
})

test('keeps the closed mobile sidebar out of keyboard navigation', async () => {
  const source = await chatSource()

  assert.match(source, /:inert="isMobile && !sidebarOpen"/)
  assert.match(source, /:aria-hidden="isMobile && !sidebarOpen"/)
})

test('shows only a direct share action for mobile answer tools', async () => {
  const source = await chatSource()

  assert.match(
    source,
    /v-if="isMobile && !isAnonymous && message\.run"\s+type="button"\s+class="icon-btn mobile-share-btn"/
  )
  assert.doesNotMatch(source, /messageSecondaryActions\(message\)/)
  assert.doesNotMatch(source, /handleMessageAction\(message, \$event\)/)
})

test('reduces secondary account information in the mobile drawer', async () => {
  const source = await userDockSource()

  assert.match(source, /v-if="!isMobile" class="truncate text-xs/)
  assert.match(source, /'dock-trigger-mobile': isMobile/)
})

test('creates the first session only when the user submits a prompt', async () => {
  const source = await chatSource()
  const submit = source.indexOf('async function submit()')
  const createFirstSession = source.indexOf(
    'await createNewSession(false)',
    submit
  )
  const bindSession = source.indexOf(
    'const sessionAtSubmit = selectedSessionUuid.value',
    submit
  )
  const submitGuard = source.indexOf('if (loading.value.run)', submit)
  const markSubmitting = source.indexOf('loading.value.run = true', submit)

  assert.notEqual(createFirstSession, -1)
  assert.notEqual(bindSession, -1)
  assert.notEqual(submitGuard, -1)
  assert.ok(submitGuard < createFirstSession)
  assert.ok(markSubmitting < createFirstSession)
  assert.ok(createFirstSession < bindSession)
})

test('keeps every conversation layout free of repeated message avatars', async () => {
  const source = await chatSource()

  assert.doesNotMatch(source, /class="message-avatar/)
  assert.doesNotMatch(source, /\.message-avatar/)
  assert.doesNotMatch(source, /const avatarBgColor = computed/)
})

test('keeps the mobile composer docked below its prompt suggestions', async () => {
  const source = await chatSource()
  const promptSuggestions = source.indexOf('class="prompt-suggestions"')
  const composer = source.indexOf('class="composer"', promptSuggestions)

  assert.notEqual(promptSuggestions, -1)
  assert.notEqual(composer, -1)
  assert.ok(promptSuggestions < composer)
  assert.match(
    source,
    /\.main-shell \.composer-wrap,\s*\.main-shell \.composer-wrap-empty \{[\s\S]*?position: absolute;[\s\S]*?top: auto;[\s\S]*?bottom: calc\(0\.75rem \+ env\(safe-area-inset-bottom\)\);[\s\S]*?transform: none;/
  )
  assert.match(source, /\.prompt-suggestions \{[^}]*margin: 0 auto 0\.75rem;/)
  assert.doesNotMatch(source, /top: 49dvh;/)
})

test('tracks the visual viewport so keyboard panning keeps the thread top reachable', async () => {
  const source = await chatSource()

  assert.match(
    source,
    /class="lens-chat-page qa-screen-view"\s+:style="mobileViewportStyle"/
  )
  assert.match(source, /'--chat-viewport-height': `\$\{viewport\.height\}px`/)
  assert.match(
    source,
    /'--chat-viewport-offset-top': `\$\{viewport\.offsetTop\}px`/
  )
  assert.match(
    source,
    /window\.visualViewport\?\.addEventListener\(\s*'resize',\s*syncMobileViewport\s*\)/
  )
  assert.match(
    source,
    /window\.visualViewport\?\.addEventListener\(\s*'scroll',\s*syncMobileViewport\s*\)/
  )
  assert.match(
    source,
    /@media \(max-width: 1023px\) \{[\s\S]*?\.lens-chat-page \{[\s\S]*?position: fixed;[\s\S]*?top: var\(--chat-viewport-offset-top, 0px\);[\s\S]*?right: 0;[\s\S]*?bottom: auto;[\s\S]*?left: 0;[\s\S]*?height: var\(--chat-viewport-height, 100dvh\);[\s\S]*?overflow: hidden;[\s\S]*?overscroll-behavior: none;/
  )
})

test('keeps the mobile AI disclaimer in the scrolling thread', async () => {
  const source = await chatSource()
  const mobileDisclaimer = source.indexOf(
    'class="disclaimer mobile-disclaimer"'
  )
  const composerWrap = source.indexOf('class="composer-wrap"')

  assert.notEqual(mobileDisclaimer, -1)
  assert.notEqual(composerWrap, -1)
  assert.ok(mobileDisclaimer < composerWrap)
  assert.match(source, /v-if="!isMobile" class="disclaimer"/)
  assert.match(
    source,
    /\.main-shell \.composer-wrap,\s*\.main-shell \.composer-wrap-empty \{[^}]*background: transparent;/
  )
  assert.match(
    source,
    /\.main-shell \.composer-wrap,\s*\.main-shell \.composer-wrap-empty \{[^}]*background: transparent;[\s\S]*?\.composer \{[\s\S]*?box-shadow:[\s\S]*?0 10px 30px/
  )
  assert.doesNotMatch(source, /\.mobile-disclaimer \{[^}]*position: absolute;/)
})

test('keeps the mobile welcome copy clear of the docked composer', async () => {
  const source = await chatSource()

  assert.match(source, /\.chat-welcome \{[\s\S]*?padding: 0 1\.5rem 13\.5rem;/)
})

test('uses a compact disclosure for live analysis on mobile', async () => {
  const source = await chatSource()

  assert.match(
    source,
    /v-if="isRunActive && liveStructuredProgress\.items\.length"\s+class="runtime-progress-card runtime-progress-live"\s+:open="!isMobile"/
  )
  assert.match(
    source,
    /class="runtime-progress-summary runtime-progress-live-summary"[\s\S]*?\{\{ liveProgressText \}\}/
  )
  assert.match(source, /class="runtime-progress-content"/)
  assert.match(
    source,
    /\.runtime-progress-live > \.runtime-progress-summary \{[\s\S]*?display: none;/
  )
  assert.match(
    source,
    /\.runtime-progress-card \{[\s\S]*?border: 0;[\s\S]*?background: transparent;[\s\S]*?padding: 0;/
  )
  assert.match(
    source,
    /\.runtime-progress-live > \.runtime-progress-summary \{[\s\S]*?display: flex;[\s\S]*?min-height: 2\.75rem;/
  )
})
