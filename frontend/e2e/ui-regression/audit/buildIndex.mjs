#!/usr/bin/env node
/**
 * Split one big audit result into PER-ROUTE report files + a small index page,
 * so each report maps to a page/scenario instead of one endless scroll.
 *
 * Used two ways:
 *   - imported: buildSplitReports(result, outDir, lang)  ← the CLI calls this
 *   - standalone: node buildIndex.mjs <result.json> <out-dir> [lang]
 *
 * Produces in <out-dir>:
 *   index.html          overview: per-route pass/warn/fail counts
 *   <route>.html        a filterable report for that route only
 *   all.html            the full report (all routes), also filterable
 */
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

import { renderHtml } from './renderReport.mjs'

function LABELS(lang) {
  return lang === 'zh-CN'
    ? {
        title: '视觉审计 · 索引',
        page: '页面/场景',
        pass: '通过',
        warn: '警告',
        fail: '失败',
        total: '合计',
        all: '查看全部',
        sub: '按页面拆分，点击进入各页面的详细报告'
      }
    : {
        title: 'Visual audit · index',
        page: 'page / scenario',
        pass: 'pass',
        warn: 'warn',
        fail: 'fail',
        total: 'total',
        all: 'View all',
        sub: 'Split by page — click a row for that page’s detailed report'
      }
}

const esc = (s) =>
  String(s || '').replace(
    /[&<>"]/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])
  )

function indexHtml(result, rows, lang) {
  const T = LABELS(lang)
  const pill = (n, cls) =>
    n
      ? `<span class="pill ${cls}">${n}</span>`
      : `<span class="pill zero">0</span>`
  const trows = rows
    .sort((a, b) => b.fail - a.fail || b.warn - a.warn)
    .map(
      (r) =>
        `<tr onclick="location.href='${r.file}'">
        <td class="page">${esc(r.route)}</td>
        <td>${pill(r.fail, 'fail')}</td>
        <td>${pill(r.warn, 'warn')}</td>
        <td>${pill(r.pass, 'pass')}</td>
        <td class="tot">${r.total}</td>
      </tr>`
    )
    .join('')
  return `<!doctype html><html lang="${lang}"><head><meta charset="utf-8">
<title>${esc(T.title)}</title><style>
 body{font:15px/1.6 system-ui,sans-serif;margin:32px;color:#111;background:#fafafa}
 h1{font-size:20px;margin:0 0 4px} .sub{color:#666;margin:0 0 18px}
 table{border-collapse:collapse;width:100%;max-width:680px;background:#fff;border:1px solid #e5e5e5;border-radius:10px;overflow:hidden}
 th,td{padding:11px 14px;text-align:left;border-bottom:1px solid #f0f0f0}
 th{background:#f4f4f5;font-size:12px;text-transform:uppercase;color:#666}
 tr:hover td{background:#f8fafc;cursor:pointer}
 td.page{font-weight:600} td.tot{color:#666} td:not(.page):not(.tot){text-align:center}
 .pill{display:inline-block;min-width:22px;padding:2px 8px;border-radius:999px;font-weight:700;font-size:12px;color:#fff}
 .pill.fail{background:#dc2626}.pill.warn{background:#d97706}.pill.pass{background:#16a34a}.pill.zero{background:#e5e7eb;color:#9ca3af}
 .allbtn{display:inline-block;margin:16px 0 0;padding:8px 14px;border:1px solid #ccc;border-radius:8px;text-decoration:none;color:#111;background:#fff}
</style></head><body>
 <h1>${esc(T.title)}</h1>
 <p class="sub">${esc(T.sub)} · ${T.pass} ${result.passed} / ${T.warn} ${
   result.warned || 0
 } / ${T.fail} ${result.failed || 0}</p>
 <table>
   <tr><th>${T.page}</th><th>🔴 ${T.fail}</th><th>🟡 ${T.warn}</th><th>🟢 ${
     T.pass
   }</th><th>${T.total}</th></tr>
   ${trows}
 </table>
 <a class="allbtn" href="all.html">${T.all} →</a>
</body></html>`
}

/**
 * Split a cross-check result into per-route report files + an index page.
 * Exported so the CLI can produce the whole set in one command.
 */
export function buildSplitReports(result, outDir, lang = 'zh-CN') {
  const T = LABELS(lang)
  mkdirSync(outDir, { recursive: true })

  const groups = {}
  for (const r of result.rows) {
    const route = String(r.id).split('·')[0].trim()
    ;(groups[route] = groups[route] || []).push(r)
  }
  const slug = (s) => s.replace(/[^a-z0-9-]+/gi, '-').toLowerCase()
  const counts = (list) => {
    const c = { pass: 0, warn: 0, fail: 0 }
    for (const r of list) c[r.severity || 'pass']++
    return c
  }

  const rows = []
  for (const [route, grp] of Object.entries(groups)) {
    const c = counts(grp)
    const file = `${slug(route)}.html`
    const sub = {
      total: grp.length,
      passed: c.pass,
      warned: c.warn,
      failed: c.fail,
      needsHuman: 0,
      rows: grp
    }
    writeFileSync(
      join(outDir, file),
      renderHtml(sub, `${route} · 视觉审计`, lang)
    )
    rows.push({ route, file, ...c, total: grp.length })
  }
  writeFileSync(join(outDir, 'all.html'), renderHtml(result, T.title, lang))
  writeFileSync(join(outDir, 'index.html'), indexHtml(result, rows, lang))
  return { routes: rows.length, dir: outDir }
}

// Standalone entry point — only when run directly, NOT when imported (else it
// would try to read the importing script's argv as a result file).
if (import.meta.url === `file://${process.argv[1]}`) {
  const [, , resultPath, outDir, lang = 'zh-CN'] = process.argv
  if (resultPath && outDir) {
    const result = JSON.parse(readFileSync(resultPath, 'utf-8'))
    const out = buildSplitReports(result, outDir, lang)
    console.log(`wrote index.html + ${out.routes} per-route reports + all.html`)
  }
}
