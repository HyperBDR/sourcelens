import assert from 'node:assert/strict'
import test from 'node:test'

import { buildSkillEnvironmentBinding } from '../src/pages/lens/assistantEnvironment.js'

const skill = {
  uuid: 'skill-uuid',
  definition: {
    environment: [
      { name: 'API_BASE_URL', required: true },
      { name: 'API_TOKEN', required: true }
    ]
  }
}

test('reuses an existing environment set without rewriting it', () => {
  const binding = buildSkillEnvironmentBinding(skill, 'existing-set-uuid', {
    values: {}
  })

  assert.deepEqual(binding, {
    skill_uuid: 'skill-uuid',
    environment_variable_set_uuid: 'existing-set-uuid'
  })
})

test('sends only entered declared values with an existing set', () => {
  const binding = buildSkillEnvironmentBinding(skill, 'existing-set-uuid', {
    values: {
      API_BASE_URL: '',
      API_TOKEN: 'new-token',
      UNDECLARED: 'ignored'
    }
  })

  assert.deepEqual(binding, {
    skill_uuid: 'skill-uuid',
    environment_variable_set_uuid: 'existing-set-uuid',
    environment_values: [{ key: 'API_TOKEN', value: 'new-token' }]
  })
})

test('sends a named new set in the assistant payload', () => {
  const binding = buildSkillEnvironmentBinding(skill, '__new__', {
    name: 'Jira - Production',
    values: {
      API_BASE_URL: 'https://jira.example.com',
      API_TOKEN: 'production-token'
    }
  })

  assert.deepEqual(binding, {
    skill_uuid: 'skill-uuid',
    environment_variable_set_uuid: null,
    environment_variable_set_name: 'Jira - Production',
    environment_values: [
      { key: 'API_BASE_URL', value: 'https://jira.example.com' },
      { key: 'API_TOKEN', value: 'production-token' }
    ]
  })
})
