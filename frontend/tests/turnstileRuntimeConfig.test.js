import assert from 'node:assert/strict'
import test from 'node:test'

import { getTurnstileConfig } from '../src/config/runtime.js'

test.afterEach(() => {
  delete globalThis.__SOURCELENS_CONFIG__
})

test('runtime configuration disables a bundled Turnstile site key', () => {
  globalThis.__SOURCELENS_CONFIG__ = {
    turnstileEnabled: false,
    turnstileSiteKey: ''
  }

  assert.deepEqual(getTurnstileConfig('bundled-key'), {
    enabled: false,
    siteKey: ''
  })
})

test('runtime configuration enables a configured Turnstile site key', () => {
  globalThis.__SOURCELENS_CONFIG__ = {
    turnstileEnabled: true,
    turnstileSiteKey: 'runtime-key'
  }

  assert.deepEqual(getTurnstileConfig('bundled-key'), {
    enabled: true,
    siteKey: 'runtime-key'
  })
})

test('empty runtime site key preserves the bundled site key', () => {
  globalThis.__SOURCELENS_CONFIG__ = {
    turnstileEnabled: true,
    turnstileSiteKey: ''
  }

  assert.deepEqual(getTurnstileConfig('bundled-key'), {
    enabled: true,
    siteKey: 'bundled-key'
  })
})

test('build configuration remains the fallback outside a container', () => {
  assert.deepEqual(getTurnstileConfig('bundled-key'), {
    enabled: true,
    siteKey: 'bundled-key'
  })
})
