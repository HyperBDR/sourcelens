import assert from 'node:assert/strict'
import test from 'node:test'

import {
  isSensitiveMcpConfigKey,
  mcpConfigToRows,
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

  for (const key of ['region', 'endpoint', 'timeout', 'transport']) {
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
