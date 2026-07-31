/**
 * UI-regression tier entry point. Pure frontend: no backend, no seed — every
 * cell of route × locale × viewport × state runs the reusable assertion
 * battery. Failures name the exact cell so a regression is trivial to locate.
 *
 * Run against a served build (see playwright.ui.config.cjs):
 *   npm run test:ui
 */
import { test } from '@playwright/test'

import { LOCALES, VIEWPORTS, checkCell } from './engine/harness.js'
import { STATES } from './engine/mockApi.js'
import { routes } from './routes.js'

for (const route of routes) {
  for (const locale of LOCALES) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      for (const state of STATES) {
        test(`${route.id} · ${locale} · ${viewport} · ${state}`, async ({
          page
        }) => {
          await checkCell(page, { route, locale, viewport, state })
        })
      }
    }
  }
}
