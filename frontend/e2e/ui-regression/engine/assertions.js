/**
 * The reusable assertion battery for the UI-regression tier.
 *
 * These detectors are the whole point of the methodology: they catch the
 * things humans skim past — untranslated strings and console noise — across
 * every page, locale, viewport and state, automatically.
 */

/**
 * Attach a console / pageerror sink. Returns a getter for collected problems.
 * Call BEFORE navigation so nothing is missed.
 */
// The browser logs this for ANY non-2xx fetch — in error/empty states we inject
// those on purpose, so it reflects the mock, not an app defect. Real
// mishandling still surfaces as a pageerror or an app-specific console line.
const DEFAULT_IGNORE = [/Failed to load resource/i]

export function collectConsoleProblems(page, { ignore = [] } = {}) {
  const problems = []
  const patterns = [...DEFAULT_IGNORE, ...ignore]
  const ignored = (text) => patterns.some((re) => re.test(text))

  page.on('console', (msg) => {
    if (!['error', 'warning'].includes(msg.type())) return
    const text = msg.text()
    if (ignored(text)) return
    problems.push(`[console.${msg.type()}] ${text}`)
  })
  page.on('pageerror', (err) => {
    const text = String(err?.message || err)
    if (ignored(text)) return
    problems.push(`[pageerror] ${text}`)
  })

  return () => problems.slice()
}

/**
 * Scan the rendered DOM for i18n leaks — vue-i18n emits the raw key path when
 * a translation is missing, so a visible `some.dotted.key` string is a strong
 * signal of an untranslated message. Complements the static key-parity check
 * (which catches keys absent from a locale file) by catching keys referenced
 * in templates but never defined at all.
 */
export async function findI18nLeaks(page) {
  const scan = () =>
    page.evaluate(() => {
    const leakPattern = /^[a-z][a-zA-Z0-9]*(\.[a-z][a-zA-Z0-9]*){2,}$/
    const leaks = new Set()
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT
    )
    let node
    while ((node = walker.nextNode())) {
      const text = node.textContent.trim()
      if (leakPattern.test(text)) leaks.add(text)
    }
    return [...leaks]
    })

  try {
    return await scan()
  } catch {
    // A late client redirect can destroy the context mid-scan; settle once.
    await page.waitForTimeout(500)
    return scan()
  }
}
