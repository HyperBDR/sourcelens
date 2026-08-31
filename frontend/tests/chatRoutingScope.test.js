import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  filterRoutingCandidates,
  toggleRoutingScopeSelection
} from '../src/pages/lens/chatRoutingScope.js'

const chatSource = () =>
  readFile(new URL('../src/pages/lens/Chat.vue', import.meta.url), 'utf8')

const routingScopePickerSource = () =>
  readFile(
    new URL(
      '../src/pages/lens/components/ParticipatingAssistantsPicker.vue',
      import.meta.url
    ),
    'utf8'
  )

test('filters participating assistants by name without changing selection', () => {
  const assistants = [
    { uuid: 'assistant-1', name: 'Repository Analyst' },
    { uuid: 'assistant-2', name: 'Knowledge Guide' },
    { uuid: 'assistant-3', name: '运营助手' }
  ]

  assert.deepEqual(filterRoutingCandidates(assistants, '  guide '), [
    assistants[1]
  ])
  assert.deepEqual(filterRoutingCandidates(assistants, '运营'), [assistants[2]])
  assert.deepEqual(filterRoutingCandidates(assistants, ''), assistants)
})

test('select-all toggles every participating assistant back to empty', () => {
  const assistants = [
    { uuid: 'assistant-1' },
    { uuid: 'assistant-2' },
    { uuid: 'assistant-3' }
  ]

  assert.deepEqual(toggleRoutingScopeSelection([], assistants), [
    'assistant-1',
    'assistant-2',
    'assistant-3'
  ])
  assert.deepEqual(toggleRoutingScopeSelection(['assistant-1'], assistants), [
    'assistant-1',
    'assistant-2',
    'assistant-3'
  ])
  assert.deepEqual(
    toggleRoutingScopeSelection(
      ['assistant-1', 'assistant-2', 'assistant-3'],
      assistants
    ),
    []
  )
})

test('Smart Collaboration starts with an empty searchable routing scope', async () => {
  const [source, picker] = await Promise.all([
    chatSource(),
    routingScopePickerSource()
  ])

  assert.match(picker, /:value="query"\s+type="search"/)
  assert.match(picker, /@click="\$emit\('toggle-all'\)"/)
  assert.match(source, /routingScopeDraft\.value = \[\]/)
  assert.match(
    source,
    /async function createNewSession\(\s*notify = true,\s*allowedAssistantUuids = \[\]\s*\)/
  )
  assert.match(
    source,
    /await createNewSession\(\s*false,\s*routingScopeAssistantUuids\.value\s*\)/
  )
  assert.match(picker, /participatingAssistantsTitle/)
  assert.match(picker, /routing-scope-entry/)
  assert.doesNotMatch(picker, /class="routing-scope-trigger"/)
  assert.match(picker, /participatingAssistantsRecommended/)
  assert.match(picker, /routing-scope-avatar-stack/)
  assert.doesNotMatch(picker, /routing-scope-option-type/)
  assert.match(picker, /routing-scope-group-title/)
  assert.match(picker, /participatingAssistantsCount/)
})

test('participating assistant summary is localized in every locale', async () => {
  const [english, chinese, spanish] = await Promise.all(
    ['en', 'zh-CN', 'es'].map((locale) =>
      readFile(
        new URL(`../src/locales/${locale}.json`, import.meta.url),
        'utf8'
      ).then(JSON.parse)
    )
  )

  assert.equal(
    english.lens.chat.participatingAssistants,
    'Participating assistants · {count}'
  )
  assert.equal(chinese.lens.chat.participatingAssistants, '参与助手 · {count}')
  assert.equal(
    spanish.lens.chat.participatingAssistants,
    'Asistentes participantes · {count}'
  )
})

test('Smart Collaboration exposes the picker above the composer', async () => {
  const [chat, picker] = await Promise.all([
    chatSource(),
    routingScopePickerSource()
  ])

  assert.match(
    chat,
    /<div class="composer-shell relative">\s+<ParticipatingAssistantsPicker\s+v-if="isSmartCollaborationConversation"/
  )
  assert.match(chat, /:mobile="isMobile"/)
  assert.match(picker, /:class="\{ 'is-mobile': mobile \}"/)
  assert.match(picker, /class="routing-scope-panel"/)
  assert.match(picker, /role="dialog"/)
  assert.match(picker, /class="routing-scope-recommend"/)
  assert.match(picker, /candidates: \{ type: Array/)
  assert.match(picker, /selectedUuids: \{ type: Array/)
  assert.match(chat, /v-model:draft="routingScopeDraft"/)
  assert.match(chat, /:candidates="routingCandidates"/)
  assert.match(chat, /:selected-uuids="routingScopeAssistantUuids"/)
})
