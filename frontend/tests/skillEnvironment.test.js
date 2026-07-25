import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildSkillEnvironment,
  SHELL_ENVIRONMENT_NAME_PATTERN,
  skillEnvironmentForm
} from '../src/pages/lens/skillEnvironment.js'

test('uses portable uppercase Shell environment variable names', () => {
  const pattern = new RegExp(`^(?:${SHELL_ENVIRONMENT_NAME_PATTERN})$`)
  const validNames = ['API_TOKEN', '_PRIVATE_KEY', 'SERVICE_URL_2']
  const invalidNames = [
    '2FA_TOKEN',
    'api_token',
    'API-TOKEN',
    'API.TOKEN',
    'API TOKEN',
    'API=TOKEN'
  ]

  for (const name of validNames) {
    assert.equal(pattern.test(name), true, name)
  }
  for (const name of invalidNames) {
    assert.equal(pattern.test(name), false, name)
  }
})

test('builds a normalized environment declaration for Skill uploads', () => {
  assert.deepEqual(
    buildSkillEnvironment([
      {
        name: '  API_TOKEN  ',
        description: '  Access token  ',
        secret: false
      }
    ]),
    [
      {
        name: 'API_TOKEN',
        description: 'Access token',
        required: true,
        secret: true
      }
    ]
  )
})

test('creates editable form rows from an uploaded Skill declaration', () => {
  assert.deepEqual(
    skillEnvironmentForm([
      {
        name: 'SERVICE_URL',
        description: 'Service endpoint',
        required: false,
        secret: false
      }
    ]),
    [
      {
        name: 'SERVICE_URL',
        description: 'Service endpoint',
        required: true,
        secret: false
      }
    ]
  )
})
