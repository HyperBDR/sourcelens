import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import { buildAssistantDetail } from '../src/pages/lens/assistantDetails.js'

const source = (path) =>
  readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('assistant detail preserves directories, bindings, and grants', () => {
  const detail = buildAssistantDetail({
    selected_dirs: [
      { path: '/workspace/api' },
      { path: '/workspace/frontend' }
    ],
    skill_bindings: [
      { skill_name: 'Repository search', enabled: true },
      { skill: { name: 'Release notes' }, enabled: false }
    ],
    mcp_bindings: [
      { mcp_name: 'GitHub', enabled: true },
      { mcp_server: { name: 'Sentry' }, enabled: false }
    ],
    access_grants: [
      {
        type: 'user',
        id: 7,
        username: 'ada',
        email: 'ada@example.com'
      },
      { type: 'group', id: 3, name: 'Platform' }
    ]
  })

  assert.deepEqual(detail.workspaceDirectories, [
    '/workspace/api',
    '/workspace/frontend'
  ])
  assert.deepEqual(detail.skills, [
    { name: 'Repository search', enabled: true },
    { name: 'Release notes', enabled: false }
  ])
  assert.deepEqual(detail.mcps, [
    { name: 'GitHub', enabled: true },
    { name: 'Sentry', enabled: false }
  ])
  assert.deepEqual(detail.authorizedUsers, [
    {
      id: 7,
      username: 'ada',
      email: 'ada@example.com'
    }
  ])
  assert.deepEqual(detail.authorizedGroups, [{ id: 3, name: 'Platform' }])
})

test('assistant detail safely normalizes incomplete list data', () => {
  const detail = buildAssistantDetail({
    selected_dirs: ['/workspace/docs', null],
    skill_bindings: [{ skill_uuid: 'skill-1' }],
    mcp_bindings: [{ mcp_uuid: 'mcp-1' }],
    access_grants: [{ type: 'user', id: 9, name: 'grace' }]
  })

  assert.deepEqual(detail.workspaceDirectories, ['/workspace/docs'])
  assert.deepEqual(detail.skills, [{ name: 'skill-1', enabled: true }])
  assert.deepEqual(detail.mcps, [{ name: 'mcp-1', enabled: true }])
  assert.deepEqual(detail.authorizedUsers, [
    { id: 9, username: 'grace', email: '' }
  ])
  assert.deepEqual(detail.authorizedGroups, [])
})

test('assistant list delegates lower-frequency data to a drawer', async () => {
  const [page, drawer, button] = await Promise.all([
    source('pages/lens/Assistants.vue'),
    source('pages/lens/AssistantDetailDrawer.vue'),
    source('components/ui/BaseButton.vue')
  ])

  assert.doesNotMatch(page, /row\.selected_dirs\?\.\[0\]\?\.path/)
  assert.doesNotMatch(page, /\{\{ shareUrl\(row\) \}\}/)
  assert.match(page, /AssistantDetailDrawer/)
  assert.match(page, /data-testid="assistant-tool-counts"/)
  assert.match(page, /:aria-label="skillCountLabel\(row\)"/)
  assert.match(page, /:aria-label="mcpCountLabel\(row\)"/)
  assert.match(page, /<BaseModal[\s\S]*archiveTitle/)
  assert.match(page, /variant="danger-outline"/)
  assert.match(button, /'danger-outline'/)
  assert.doesNotMatch(page, /archiveConfirmUuid/)
  assert.match(
    page,
    new RegExp(
      'function startEditFromDetail\\(row\\) \\{\\s*' +
        'closeDetails\\(\\)\\s*startEdit\\(row\\)'
    )
  )
  assert.match(drawer, /data-testid="assistant-detail-directories"/)
  assert.match(drawer, /data-testid="assistant-detail-skills"/)
  assert.match(drawer, /data-testid="assistant-detail-mcps"/)
  assert.match(drawer, /data-testid="assistant-detail-access"/)
  assert.match(drawer, /v-if="visibility === 'private'"/)
  assert.match(drawer, /:disabled="assistant.status !== 'active'"/)
  assert.match(drawer, /\$emit\('edit', assistant\)/)
})

test('assistant management loads form resources only when editing', async () => {
  const page = await source('pages/lens/Assistants.vue')

  assert.match(page, /async function loadFormResources\(\)/)
  assert.match(page, /await loadFormResources\(\)/)
  assert.doesNotMatch(
    page,
    /async function load\(\)[\s\S]*?Promise\.all\(\[\s*listAssistants[\s\S]*?listSkills/
  )
})
