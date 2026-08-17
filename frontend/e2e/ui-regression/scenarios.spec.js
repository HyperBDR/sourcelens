/**
 * Scenario-tier entry point: run each scenario's atomic steps in order,
 * checking the middle of the flow (not just the final screen). Emits one
 * manifest row per STEP, each carrying that step's explicit expectation as the
 * basis for the visual audit.
 */
import { test } from '@playwright/test'

import { runScenario } from './engine/runScenario.js'
import { installMocks } from './engine/mockApi.js'
import { scenarios } from './scenarios.js'

const LOCALES = ['en', 'zh-CN']

async function seed(page, locale) {
  await page.addInitScript((loc) => {
    localStorage.setItem('userLanguage', loc)
  }, locale)
}

for (const scenario of scenarios) {
  for (const locale of LOCALES) {
    test(`scenario: ${scenario.id} · ${locale}`, async ({ page }) => {
      await page.setViewportSize({ width: 1280, height: 800 })
      await seed(page, locale)
      // Install the scenario's mocks (a fake route context) before any step.
      await installMocks(page, { mocks: scenario.mocks || {} }, 'error')
      await runScenario(page, {
        scenario,
        locale,
        state: 'error',
        seed: null
      })
    })
  }
}
