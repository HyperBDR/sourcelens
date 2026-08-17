/**
 * The reusable walk: for every route, drive the assertion battery across the
 * full matrix — locale × viewport × state. This loop is identical in any
 * project; only the route registry and fixtures change.
 */
import { appendFileSync, mkdirSync } from 'node:fs'

import { expect } from '@playwright/test'

import { collectConsoleProblems, findI18nLeaks } from './assertions.js'
import { installMocks } from './mockApi.js'

export const LOCALES = ['en', 'zh-CN']
export const VIEWPORTS = {
  desktop: { width: 1280, height: 800 },
  mobile: { width: 390, height: 844 }
}

const SHOT_DIR = 'test-results/ui-regression'
const MANIFEST = `${SHOT_DIR}/manifest.jsonl`

// Append one manifest row per cell (JSONL, append-only so parallel workers
// never clobber each other). The audit CLI consumes this to cross-check every
// cell's deterministic result against the visual oracle.
function recordManifest(row) {
  mkdirSync(SHOT_DIR, { recursive: true })
  appendFileSync(MANIFEST, JSON.stringify(row) + '\n')
}

/**
 * Seed the locale so the page boots in the target language, and mark auth so
 * guarded routes render instead of redirecting. Kept minimal on purpose —
 * projects extend `seedStorage` via the route registry if they need more.
 */
async function seed(page, { locale, route }) {
  await page.addInitScript(
    ([loc, authed, extra]) => {
      // The app reads its UI language from `userLanguage` (src/i18n/index.js);
      // seeding the wrong key silently leaves every page in the default locale.
      localStorage.setItem('userLanguage', loc)
      // Auth is opt-in per route: an authenticated route seeds a token so it
      // renders instead of redirecting to /login; an anonymous route (e.g.
      // /login itself) must NOT, or the app bounces a "logged-in" user away.
      if (authed) localStorage.setItem('access_token', 'ui-regression-token')
      for (const [key, value] of Object.entries(extra || {})) {
        localStorage.setItem(key, value)
      }
    },
    [locale, !!route.authed, route.seedStorage || {}]
  )
}

/**
 * Run the battery for one cell of the matrix. Returns nothing; asserts inline
 * so Playwright reports the exact failing (route, locale, viewport, state).
 */
export async function checkCell(page, { route, locale, viewport, state }) {
  await page.setViewportSize(VIEWPORTS[viewport])
  await seed(page, { locale, route })
  await installMocks(page, route, state)

  const consoleProblems = collectConsoleProblems(page, {
    ignore: route.ignoreConsole || []
  })

  await page.goto(route.path)
  // Not networkidle: this app holds persistent connections (WebSocket /
  // polling) so the network never idles. Wait for the Vue root to render
  // content instead, then let it settle briefly.
  await page.waitForFunction(
    () => document.querySelector('#app')?.children.length > 0,
    { timeout: 15000 }
  )
  // Let any post-render client redirect settle before we read the DOM, so the
  // evaluate below never races a navigation that destroys its context.
  await page.waitForTimeout(500)

  // Screenshot every cell — the artifact trail the visual-audit oracle reads.
  const shot = `${SHOT_DIR}/${route.id}__${locale}__${viewport}__${state}.png`
  await page.screenshot({ path: shot, fullPage: true })

  // Record a manifest row for EVERY cell (in finally, so a failing assertion
  // still logs the row) — this is what feeds the automated visual cross-check.
  let deterministic = 'pass'
  try {
    // Proof-of-exercise: the locale sentinel must be present, so a silently
    // non-applied language axis fails here deterministically (no eyeballing).
    if (route.sentinels?.[locale]) {
      await expect(
        page.getByText(route.sentinels[locale], { exact: false }).first(),
        `locale sentinel "${route.sentinels[locale]}" on ${route.id} [${locale}]`
      ).toBeVisible()
    }

    const leaks = await findI18nLeaks(page)
    expect(leaks, `i18n leaks on ${route.id} [${locale}]`).toEqual([])

    const problems = consoleProblems()
    expect(
      problems,
      `console problems on ${route.id} [${locale}/${viewport}]`
    ).toEqual([])
  } catch (err) {
    deterministic = 'fail'
    throw err
  } finally {
    recordManifest({
      // `id` carries the machine dimensions (page/locale/viewport/state) for
      // humans. The visual `intent` must stay PURE natural language — never mix
      // in tags like "[state=success]", or the model treats the tag as a
      // requirement to verify and judges against something that isn't there.
      id: `${route.id} · ${locale} · ${viewport} · ${state}`,
      intent:
        route.intent?.[locale] || route.intent?.en || 'Page renders correctly.',
      screenshot: shot,
      locale,
      viewport,
      state,
      deterministic
    })
  }
}
