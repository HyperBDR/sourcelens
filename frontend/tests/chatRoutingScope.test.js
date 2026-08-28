import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  filterRoutingCandidates,
  toggleRoutingScopeSelection
} from '../src/pages/lens/chatRoutingScope.js'

const chatSource = () =>
  readFile(new URL('../src/pages/lens/Chat.vue', import.meta.url), 'utf8')

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
  const source = await chatSource()

  assert.match(source, /v-model="routingScopeQuery"\s+type="search"/)
  assert.match(source, /@click="toggleAllRoutingAssistants"/)
  assert.match(source, /routingScopeDraft\.value = \[\]/)
  assert.match(
    source,
    /async function createNewSession\(\s*notify = true,\s*allowedAssistantUuids = \[\]\s*\)/
  )
  assert.match(
    source,
    /await createNewSession\(\s*false,\s*routingScopeAssistantUuids\.value\s*\)/
  )
  assert.match(source, /participatingAssistantsAccuracyWarning/)
})
