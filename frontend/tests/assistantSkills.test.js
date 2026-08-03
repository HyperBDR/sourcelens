import assert from 'node:assert/strict'
import test from 'node:test'

import { filterSelectableSkills } from '../src/pages/lens/assistantSkills.js'

const skills = [
  {
    uuid: 'jira',
    name: 'Jira Issues',
    slug: 'jira-issues',
    definition: {
      description: 'Search project tickets',
      environment: [{ name: 'JIRA_TOKEN', required: true }]
    }
  },
  {
    uuid: 'github',
    name: 'GitHub Pull Requests',
    slug: 'github-prs',
    package_manifest: { description: 'Review repository changes' }
  },
  {
    uuid: 'guide',
    name: 'Workspace Guide',
    slug: 'project-workspace-guide'
  }
]

test('returns every selectable Skill when the keyword is empty', () => {
  const results = filterSelectableSkills(skills, '')

  assert.deepEqual(
    results.map((skill) => skill.uuid),
    ['jira', 'github']
  )
})

test('searches Skills by name, slug, and description without case sensitivity', () => {
  assert.deepEqual(
    filterSelectableSkills(skills, 'JIRA').map((skill) => skill.uuid),
    ['jira']
  )
  assert.deepEqual(
    filterSelectableSkills(skills, 'github-prs').map((skill) => skill.uuid),
    ['github']
  )
  assert.deepEqual(
    filterSelectableSkills(skills, 'repository changes').map(
      (skill) => skill.uuid
    ),
    ['github']
  )
})

test('preserves environment declarations on filtered Skills', () => {
  const [result] = filterSelectableSkills(skills, 'tickets')

  assert.deepEqual(result.definition.environment, [
    { name: 'JIRA_TOKEN', required: true }
  ])
})
