#!/usr/bin/env node
/**
 * One-command visual audit: read the manifest produced by the UI-regression
 * run, judge every screenshot with the configured vision backend, and emit a
 * split, filterable, indexed report set.
 *
 *   AUDIT_VISION_BASE_URL=... AUDIT_VISION_API_KEY=... AUDIT_VISION_MODEL=... \
 *   node e2e/ui-regression/audit/run.mjs [--lang zh-CN] [--out <dir>]
 *
 * Prereq: `npm run test:ui` (writes test-results/ui-regression/manifest.jsonl
 * + screenshots). This script turns that into the audit reports.
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs'

import { buildSplitReports } from './buildIndex.mjs'
import { crossCheck, formatReport } from './crossCheck.mjs'

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`)
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback
}

const lang = arg('lang', 'zh-CN')
const outDir = arg('out', 'test-results/audit-reports')
const manifestPath = 'test-results/ui-regression/manifest.jsonl'

if (!existsSync(manifestPath)) {
  console.error(
    `No manifest at ${manifestPath}. Run \`npm run test:ui\` first.`
  )
  process.exit(2)
}

// Load manifest (JSONL) and make screenshot paths absolute-from-cwd.
const cwd = process.cwd()
const cases = readFileSync(manifestPath, 'utf-8')
  .split('\n')
  .filter((l) => l.trim())
  .map((l) => JSON.parse(l))
  .map((c) => ({
    ...c,
    screenshot: c.screenshot.startsWith('/')
      ? c.screenshot
      : `${cwd}/${c.screenshot}`,
    intent:
      typeof c.intent === 'object'
        ? c.intent[lang] || c.intent.en || Object.values(c.intent)[0]
        : c.intent,
    noteLang: lang
  }))

// Inject the standalone vision backend (env-configured, side-channel).
const { default: judge } = await import('./backends/openaiVision.mjs')

console.log(`Auditing ${cases.length} screenshots with the vision backend...`)
const result = await crossCheck(cases, judge)
console.log(formatReport(result))

writeFileSync(
  `${outDir.replace(/\/$/, '')}/../audit-result.json`,
  JSON.stringify(result, null, 2)
)
const out = buildSplitReports(result, outDir, lang)
console.log(
  `\nReports: ${out.dir}/index.html  (+ ${out.routes} per-page + all.html)`
)
