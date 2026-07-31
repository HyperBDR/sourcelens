import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import test from 'node:test'

/**
 * Static i18n parity check — the cheapest, browser-free detector in the
 * UI-regression methodology. It diffs the key sets of each locale pair so
 * a string translated in one language but missing in the other is surfaced
 * from code, without rendering a single page.
 *
 * Locale pairs are the only per-project input; the flatten + diff engine is
 * reusable across projects verbatim.
 */
const LOCALE_PAIRS = [
  {
    label: 'app',
    en: '../src/locales/en.json',
    zh: '../src/locales/zh-CN.json'
  },
  {
    label: 'admin',
    en: '../src/admin/locales/en.json',
    zh: '../src/admin/locales/zh-CN.json'
  }
]

function loadJson(relativePath) {
  const path = fileURLToPath(new URL(relativePath, import.meta.url))
  return JSON.parse(readFileSync(path, 'utf-8'))
}

function flattenKeys(value, prefix = '', out = new Set()) {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) {
      const next = prefix ? `${prefix}.${key}` : key
      flattenKeys(child, next, out)
    }
  } else {
    out.add(prefix)
  }
  return out
}

function missingFrom(reference, candidate) {
  return [...reference].filter((key) => !candidate.has(key)).sort()
}

for (const pair of LOCALE_PAIRS) {
  test(`i18n parity (${pair.label}): en and zh-CN cover the same keys`, () => {
    const enKeys = flattenKeys(loadJson(pair.en))
    const zhKeys = flattenKeys(loadJson(pair.zh))

    const missingInZh = missingFrom(enKeys, zhKeys)
    const missingInEn = missingFrom(zhKeys, enKeys)

    const report = [
      missingInZh.length
        ? `Missing in zh-CN (${missingInZh.length}):\n  ${missingInZh.join(
            '\n  '
          )}`
        : '',
      missingInEn.length
        ? `Missing in en (${missingInEn.length}):\n  ${missingInEn.join(
            '\n  '
          )}`
        : ''
    ]
      .filter(Boolean)
      .join('\n')

    assert.equal(
      missingInZh.length + missingInEn.length,
      0,
      `\n[${pair.label}] locale key mismatch:\n${report}`
    )
  })
}
