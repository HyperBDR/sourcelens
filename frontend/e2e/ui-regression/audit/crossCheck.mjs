/**
 * Dual-oracle cross-check — the reusable audit CRI.
 *
 * It does NOT judge screenshots itself. It orchestrates two independent
 * oracles and reconciles them:
 *   - Oracle A: the deterministic test result (pass/fail from assertions).
 *   - Oracle B: a pluggable visual judge (multimodal) that reads the final
 *     screenshot and decides whether the declared intent is satisfied.
 *
 * Rule: AGREE -> trust automatically. DISAGREE -> escalate to a human.
 * The disagreement set is where test bugs hide (e.g. a green cell whose
 * screenshot visibly violates its intent — the locale bug).
 *
 * The visual backend is INJECTED (`judge`), never hardcoded, so any project
 * wires in its own multimodal capability — this file is provider-agnostic and
 * the whole orchestration below is deterministic.
 *
 *   judge: (case) => Promise<{ satisfied: boolean, note?: string }>
 *   case:  { id, intent, screenshot, deterministic: 'pass' | 'fail' }
 */

function verdictFor(det, satisfied) {
  if (det === 'visual-only') {
    // No deterministic oracle for this step — the visual oracle is the sole
    // judge (nothing to disagree WITH). Never needs human reconciliation just
    // for lacking an assertion.
    return satisfied ? 'PASS · visual' : 'FAIL · visual'
  }
  // Two oracles present: cross-check them. A mismatch is where a green test may
  // be lying, and only THAT escalates to a human.
  const detPass = det === 'pass'
  const agree = detPass === satisfied
  return agree
    ? detPass
      ? 'AGREE · pass'
      : 'AGREE · fail'
    : 'DISAGREE → human'
}

// Bounded-concurrency map that PRESERVES input order — the visual backend is
// network-bound, so judging many screenshots serially is needlessly slow.
async function mapLimit(items, limit, fn) {
  const out = new Array(items.length)
  let next = 0
  async function worker() {
    while (next < items.length) {
      const i = next++
      out[i] = await fn(items[i], i)
    }
  }
  await Promise.all(
    Array.from({ length: Math.min(limit, items.length) }, worker)
  )
  return out
}

export async function crossCheck(cases, judge, concurrency = 6) {
  const rows = await mapLimit(cases, concurrency, async (c) => {
    const b = await judge(c)
    const verdict = verdictFor(c.deterministic, b.satisfied)
    const issues = Array.isArray(b.issues) ? b.issues : []
    // Three severities:
    //   fail — intent not met (red) or the two oracles disagree.
    //   warn — intent met, but the visual audit raised style/layout/i18n
    //          issues (yellow) — surfaced, not blocking.
    //   pass — intent met, no issues (green).
    const isFail = verdict.startsWith('DISAGREE') || verdict.startsWith('FAIL')
    const severity = isFail ? 'fail' : issues.length ? 'warn' : 'pass'
    return {
      id: c.id,
      intent: c.intent,
      screenshot: c.screenshot,
      deterministic: c.deterministic,
      visual: b.satisfied ? 'satisfied' : 'not-satisfied',
      visualNote: b.note || '',
      issues,
      verdict,
      severity
    }
  })
  const failed = rows.filter((r) => r.severity === 'fail')
  const warned = rows.filter((r) => r.severity === 'warn')
  const disagreements = rows.filter((r) => r.verdict.startsWith('DISAGREE'))
  return {
    total: rows.length,
    passed: rows.filter((r) => r.severity === 'pass').length,
    warned: warned.length,
    failed: failed.length,
    needsHuman: disagreements.length,
    // Back-compat alias used by older summary strings.
    agreed: rows.length - failed.length,
    rows,
    disagreements
  }
}

export function formatReport(result) {
  const line = (r) =>
    `  [${r.verdict}]  ${r.id}\n` +
    `      intent : ${r.intent}\n` +
    `      det=${r.deterministic}  visual=${r.visual}` +
    (r.visualNote ? `  (${r.visualNote})` : '')
  return [
    `Cross-check: ${result.total} cases · ${result.agreed} agreed · ` +
      `${result.needsHuman} need human`,
    ...result.rows.map(line),
    result.needsHuman
      ? `\n>> ${result.needsHuman} disagreement(s) — the test may be lying; ` +
        `human must adjudicate and (usually) add a deterministic sentinel.`
      : `\nAll oracles agree — no human needed.`
  ].join('\n')
}
