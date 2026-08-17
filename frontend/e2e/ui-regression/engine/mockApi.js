/**
 * Reusable mock layer for the UI-regression tier.
 *
 * The engine is project-agnostic: it intercepts every `/api/**` call and
 * answers it from the route registry's per-route `mocks` map, driven by the
 * current `state`. "Forward and reverse" mocking = the same page rendered
 * under success / empty / error states the real backend rarely reproduces.
 *
 * A route entry declares:
 *   mocks: { '<url glob>': (state) => ({ status?, json?, body?, contentType? }) }
 * Anything not matched falls through to a safe empty 200, so an un-mocked
 * call never wedges the page.
 */

const DEFAULT_UNMATCHED = { status: 200, json: [] }

function resolveResponse(factory, state) {
  const value = typeof factory === 'function' ? factory(state) : factory
  return value || DEFAULT_UNMATCHED
}

function matches(pathname, glob) {
  const escaped = glob
    .replace(/[.+^${}()|[\]\\]/g, '\\$&')
    .replace(/\*\*/g, '.*')
    .replace(/(?<!\.)\*/g, '[^/]*')
  return new RegExp(`^${escaped}$`).test(pathname)
}

const APP_HOSTS = new Set(['localhost', '127.0.0.1'])

export async function installMocks(page, route, state) {
  const entries = Object.entries(route.mocks || {})

  // Intercept ALL requests so the tier is hermetic: mock the API, let the
  // app's own assets through, and stub cross-origin externals (CDN fonts,
  // OAuth SDKs) with an empty 200 so a sandbox with no outbound network does
  // not spew console errors that would mask real findings.
  await page.route('**/*', async (handler) => {
    const url = new URL(handler.request().url())

    if (!url.pathname.startsWith('/api/')) {
      if (APP_HOSTS.has(url.hostname)) return handler.continue()
      return handler.fulfill({
        status: 200,
        contentType: 'text/plain',
        body: ''
      })
    }

    const hit = entries.find(([glob]) => matches(url.pathname, glob))
    const response = hit ? resolveResponse(hit[1], state) : DEFAULT_UNMATCHED

    const fulfill = { status: response.status || 200 }
    if (response.json !== undefined) {
      fulfill.contentType = 'application/json'
      fulfill.body = JSON.stringify(response.json)
    } else if (response.body !== undefined) {
      fulfill.contentType = response.contentType || 'text/plain'
      fulfill.body = response.body
    } else {
      fulfill.contentType = 'application/json'
      fulfill.body = JSON.stringify([])
    }
    await handler.fulfill(fulfill)
  })
}

// Snapshot layer covers the DATA dimension: success (has data) and empty (no
// data). The `error` case (a backend failure) is a BEHAVIOUR concern — for
// most read-only pages a 500 just degrades to the empty state, and a real
// error UI only appears after an action (send/submit). That belongs in the
// scenario layer (see scenarios.js), which triggers the action and asserts the
// error handling, rather than being applied blindly to every page snapshot.
export const STATES = ['success', 'empty']
