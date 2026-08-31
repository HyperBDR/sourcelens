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
  assert.match(picker, /participatingAssistantsAccuracyWarning/)
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
  assert.match(chat, /v-model:draft="routingScopeDraft"/)
})
