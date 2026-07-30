/**
 * Render a dual-oracle cross-check result to a self-contained HTML report:
 * each case shows its screenshot + intent + both oracle verdicts + the
 * AGREE/DISAGREE outcome, so the report is auditable by eye, not by trust.
 *
 * Reusable: no app imports; embeds screenshots as base64 so the file is
 * standalone. `rows` come from crossCheck() (each carries a `screenshot` path).
 */
import { readFileSync } from 'node:fs'

function img(path) {
  try {
    return `data:image/png;base64,${readFileSync(path).toString('base64')}`
  } catch {
    return ''
  }
}

const esc = (s) =>
  String(s || '').replace(
    /[&<>"]/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]
  )

// UI strings per report language — one place to add a language. The visual
// `note` itself is written in this same language by the backend (see
// systemPrompt), so the whole report reads as one language, not a mix.
const STRINGS = {
  en: {
    pass: 'PASS',
    fail: 'FAIL', warn: 'WARN',
    failReason: 'Why it failed: ', warnReason: 'Style / layout / i18n notes: ',
    noReason: 'The screen does not match the intent.',
    intent: 'intent',
    deterministic: 'deterministic test',
    visual: 'visual audit',
    note: 'visual note',
    issues: 'issues found',
    fAll: 'All', fAllRoutes: 'All pages',
    summary: (r) =>
      `${r.total} cases · ${r.passed} pass · ${r.warned || 0} warn · ${
        r.failed || 0
      } fail` +
      ` — <b>warnings are style/layout/i18n notes; failures are intent mismatches.</b>`
  },
  'zh-CN': {
    pass: '测试通过',
    fail: '测试失败', warn: '警告',
    failReason: '失败原因：', warnReason: '样式/布局/翻译提示：',
    noReason: '画面与预期不符。',
    intent: '预期',
    deterministic: '确定性测试',
    visual: '视觉审计',
    note: '视觉说明',
    issues: '发现的问题',
    fAll: '全部', fAllRoutes: '全部页面',
    summary: (r) =>
      `共 ${r.total} 项 · 通过 ${r.passed} · 警告 ${r.warned || 0} · 失败 ${
        r.failed || 0
      }` +
      ` —— <b>警告=样式/布局/翻译建议；失败=意图不符。</b>`
  }
}

export function renderHtml(result, title = 'Visual-audit cross-check', lang = 'en') {
  const S = STRINGS[lang] || STRINGS.en
  // Distinct routes (first id segment) for the route dropdown.
  const routes = [
    ...new Set(result.rows.map((r) => String(r.id).split('·')[0].trim()))
  ]
  const routeOptions = routes
    .map((rt) => `<option value="${esc(rt)}">${esc(rt)}</option>`)
    .join('')
  const card = (r) => {
    // Three severities: fail (red) / warn (yellow) / pass (green). Fall back to
    // verdict for older result files without a severity field.
    const sev =
      r.severity ||
      (r.verdict.startsWith('DISAGREE') || r.verdict.startsWith('FAIL')
        ? 'fail'
        : 'pass')
    const status = sev === 'fail' ? S.fail : sev === 'warn' ? S.warn : S.pass
    const banner =
      sev === 'fail'
        ? `<div class="conflict fail"><b>${S.failReason}</b>${esc(
            r.visualNote || S.noReason
          )}</div>`
        : sev === 'warn'
          ? `<div class="conflict warn"><b>${S.warnReason}</b>${esc(
              r.visualNote || ''
            )}</div>`
          : ''
    // route = first segment of the id ("login · en · desktop · success").
    const route = String(r.id).split('·')[0].trim()
    return `
    <div class="card ${sev}" data-sev="${sev}" data-route="${esc(route)}">
      <div class="head">
        <span class="badge">${status}</span>
        <span class="id">${esc(r.id)}</span>
      </div>
      ${banner}
      <div class="body">
        <img src="${img(r.screenshot)}" alt="${esc(r.id)}" />
        <dl>
          <dt>${S.intent}</dt><dd>${esc(r.intent)}</dd>
          <dt>${S.deterministic}</dt><dd>${esc(r.deterministic)}</dd>
          <dt>${S.visual}</dt><dd>${esc(r.visual)}</dd>
          <dt>${S.note}</dt><dd>${esc(r.visualNote)}</dd>
          ${
            r.issues && r.issues.length
              ? `<dt>${S.issues}</dt><dd><ul class="issues">${r.issues
                  .map((it) => `<li>${esc(it)}</li>`)
                  .join('')}</ul></dd>`
              : ''
          }
        </dl>
      </div>
    </div>`
  }
  return `<!doctype html><html lang="${lang}"><head><meta charset="utf-8">
<title>${esc(title)}</title><style>
 body{font:14px/1.5 system-ui,sans-serif;margin:24px;color:#111;background:#fafafa}
 h1{font-size:18px} .sum{margin:0 0 16px;color:#444}
 .card{border:1px solid #ddd;border-radius:10px;margin:14px 0;overflow:hidden;background:#fff}
 .card.pass{border-left:6px solid #16a34a}.card.warn{border-left:6px solid #d97706}.card.fail{border-left:6px solid #dc2626}
 .conflict{margin:0;padding:10px 14px;font-weight:600;border-top:1px solid;border-bottom:1px solid}
 .conflict.fail{background:#fef2f2;color:#991b1b;border-color:#fecaca}
 .conflict.warn{background:#fffbeb;color:#92400e;border-color:#fde68a}
 .head{display:flex;gap:10px;align-items:center;padding:10px 14px;background:#f4f4f5}
 .badge{font-weight:700;font-size:12px;padding:3px 8px;border-radius:999px;color:#fff}
 .pass .badge{background:#16a34a}.warn .badge{background:#d97706}.fail .badge{background:#dc2626}
 .id{font-weight:600} .body{display:grid;grid-template-columns:minmax(0,1.4fr) 1fr;gap:16px;padding:14px}
 img{width:100%;border:1px solid #eee;border-radius:6px}
 dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:4px 12px;align-content:start}
 dt{color:#666;font-size:12px;text-transform:uppercase}dd{margin:0}
 ul.issues{margin:2px 0 0;padding-left:18px}ul.issues li{color:#b45309;margin:2px 0}
 .filters{position:sticky;top:0;background:#fafafa;padding:10px 0;margin-bottom:8px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;border-bottom:1px solid #eee;z-index:5}
 .filters button{border:1px solid #ccc;background:#fff;border-radius:999px;padding:5px 12px;cursor:pointer;font:inherit}
 .filters button.active{background:#111;color:#fff;border-color:#111}
 .filters select{padding:5px 10px;border-radius:8px;border:1px solid #ccc;font:inherit}
 .card.hidden{display:none}
 @media(max-width:720px){.body{grid-template-columns:1fr}}
</style></head><body>
 <h1>${esc(title)}</h1>
 <p class="sum">${S.summary(result)}</p>
 <div class="filters">
   <button data-f="all" class="active">${S.fAll} (${result.total})</button>
   <button data-f="fail">🔴 ${S.fail} (${result.failed || 0})</button>
   <button data-f="warn">🟡 ${S.warn} (${result.warned || 0})</button>
   <button data-f="pass">🟢 ${S.pass} (${result.passed || 0})</button>
   <select id="route"><option value="all">${S.fAllRoutes}</option>${routeOptions}</select>
 </div>
 <div id="cards">${result.rows.map(card).join('')}</div>
 <script>
   const sevBtns=[...document.querySelectorAll('.filters button')];
   const routeSel=document.getElementById('route');
   let sev='all';
   function apply(){
     const rt=routeSel.value;
     for(const c of document.querySelectorAll('#cards .card')){
       const okSev = sev==='all' || c.dataset.sev===sev;
       const okRt = rt==='all' || c.dataset.route===rt;
       c.classList.toggle('hidden', !(okSev&&okRt));
     }
   }
   sevBtns.forEach(b=>b.onclick=()=>{sev=b.dataset.f;sevBtns.forEach(x=>x.classList.toggle('active',x===b));apply();});
   routeSel.onchange=apply;
 </script>
</body></html>`
}
