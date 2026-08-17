#!/usr/bin/env node
/**
 * Visual-audit CLI — reusable, project-agnostic.
 *
 * Reconciles the deterministic Playwright result (oracle A) with a pluggable
 * multimodal visual judge (oracle B) over a report, and flags DISAGREEMENTS
 * for human review. The visual backend is a runtime parameter (`--judge`),
 * never hardcoded — any project injects its own multimodal capability.
 *
 * Usage:
 *   node cli.mjs --manifest <cases.json> --judge <./backend.mjs> [--gate]
 *
 *   manifest: [{ id, intent, screenshot, deterministic: 'pass'|'fail' }]
 *   judge module: default export (case) => { satisfied: boolean, note? }
 *   --gate: exit non-zero when any disagreement needs a human.
 */
import { readFileSync, writeFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

import { buildSplitReports } from './buildIndex.mjs'
import { crossCheck, formatReport } from './crossCheck.mjs'
import { renderHtml } from './renderReport.mjs'

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`)
  return i >= 0 && process.argv[i + 1] ? process.argv[i + 1] : fallback
}

const manifestPath = arg('manifest')
const judgePath = arg('judge')
const gate = process.argv.includes('--gate')
// One language for the whole report: UI labels, chosen intent, AND the
// visual note the model writes — so the report never reads as a mix.
const lang = arg('lang', 'en')

if (!manifestPath || !judgePath) {
  console.error('usage: cli.mjs --manifest <cases.json> --judge <backend.mjs>')
  process.exit(2)
}

const raw = readFileSync(manifestPath, 'utf-8')
// Accept either a JSON array or JSONL (one object per line, as the harness
// emits). JSONL lets parallel test workers append rows without clobbering.
const cases = raw.trimStart().startsWith('[')
  ? JSON.parse(raw)
  : raw
      .split('\n')
      .filter((l) => l.trim())
      .map((l) => JSON.parse(l))
const judgeModule = await import(
  pathToFileURL(new URL(judgePath, import.meta.url).pathname).href
)
const judge = judgeModule.default

// Resolve each case to the report language: pick the matching intent variant
// (routes may carry {en, 'zh-CN'}) and tell the backend which language to
// write the note in.
const localized = cases.map((c) => ({
  ...c,
  intent:
    typeof c.intent === 'object'
      ? c.intent[lang] || c.intent.en || Object.values(c.intent)[0]
      : c.intent,
  noteLang: lang
}))

const result = await crossCheck(localized, judge)
console.log(formatReport(result))

// Persist the structured result so the report can be re-rendered offline
// (e.g. after a template change) without re-calling the vision model.
const resultPath = arg('save-result')
if (resultPath) {
  writeFileSync(resultPath, JSON.stringify(result, null, 2))
  console.log(`\nResult JSON: ${resultPath}`)
}

const htmlPath = arg('html')
if (htmlPath) {
  const reportTitle =
    lang === 'zh-CN'
      ? '视觉审计交叉核对 — 完整运行'
      : 'Visual-audit cross-check — full run'
  writeFileSync(htmlPath, renderHtml(result, reportTitle, lang))
  console.log(`\nHTML report: ${htmlPath}`)
}

// One-command output: split into per-route reports + an index page.
const splitDir = arg('split')
if (splitDir) {
  const out = buildSplitReports(result, splitDir, lang)
  console.log(
    `\nSplit reports: ${out.dir}/index.html (+ ${out.routes} per-page + all.html)`
  )
}

process.exit(gate && result.needsHuman ? 1 : 0)
