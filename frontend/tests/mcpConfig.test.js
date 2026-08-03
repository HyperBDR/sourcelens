import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildMcpEnvironment,
  isSensitiveMcpConfigKey,
  mcpConfigToRows,
  mcpEnvironmentForm,
  mcpRowsToConfig,
  MCP_CONFIG_MASK
} from '../src/pages/lens/mcpConfig.js'

test('detects MCP credential keys without masking ordinary config', () => {
  for (const key of [
    'password',
    'client-secret',
    'API_KEY',
    'accessToken',
    'Authorization',
    'private_key',
    'credential'
  ]) {
    assert.equal(isSensitiveMcpConfigKey(key), true, key)
  }

  for (const key of [
    'region',
    'endpoint',
    'timeout',
    'transport',
    'max_tokens',
    'token_limit',
    'tokenizer'
  ]) {
    assert.equal(isSensitiveMcpConfigKey(key), false, key)
  }
  assert.equal(MCP_CONFIG_MASK, '********')
})

test('preserves nested MCP config objects through the editor', () => {
  const config = {
    headers: {
      Authorization: MCP_CONFIG_MASK,
      'X-Client': 'sourcelens'
    },
    retries: 3
  }

  const rows = mcpConfigToRows(config)

  assert.deepEqual(mcpRowsToConfig(rows), config)
  assert.match(rows[0].value, /"Authorization":"\*{8}"/)
})

test('parses JSON containers entered in new MCP config rows', () => {
  const config = mcpRowsToConfig([
    {
      key: 'headers',
      value: '{"Authorization":"Bearer ${MCP_TOKEN}"}'
    },
    { key: 'scopes', value: '["issues:read","pulls:read"]' },
    { key: 'timeout', value: '30' }
  ])

  assert.deepEqual(config.headers, {
    Authorization: 'Bearer ${MCP_TOKEN}'
  })
  assert.deepEqual(config.scopes, ['issues:read', 'pulls:read'])
  assert.equal(config.timeout, '30')
})

test('preserves existing JSON-looking string values', () => {
  const config = {
    template: '{"mode":"strict"}',
    scopes: '["issues:read"]'
  }

  assert.deepEqual(mcpRowsToConfig(mcpConfigToRows(config)), config)
})

test('preserves optional MCP environment declarations', () => {
  const declarations = [
    {
      name: 'MCP_TOKEN',
      description: 'Optional access token',
      required: false,
      secret: true
    }
  ]

  assert.deepEqual(
    buildMcpEnvironment(mcpEnvironmentForm(declarations)),
    declarations
  )
})
