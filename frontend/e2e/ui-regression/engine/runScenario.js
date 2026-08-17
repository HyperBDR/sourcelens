/**
 * Scenario runner — executes a scenario's atomic steps IN ORDER, checking the
 * middle of the flow, not just the final screen. For each step it:
 *   1. runs `act` (the action)
 *   2. screenshots the resulting state
 *   3. runs `assert` (deterministic oracle) if present
 *   4. emits a manifest row carrying the step's `expect` — the basis the
 *      visual oracle later judges against (grounded, not a guess)
 *
 * Reusable: the runner is project-agnostic; only `scenarios.js` changes.
 */
import { appendFileSync, mkdirSync } from 'node:fs'

import { expect as pwExpect } from '@playwright/test'

import { installMocks } from './mockApi.js'

const SHOT_DIR = 'test-results/ui-regression'
const MANIFEST = `${SHOT_DIR}/manifest.jsonl`

function recordManifest(row) {
  mkdirSync(SHOT_DIR, { recursive: true })
  appendFileSync(MANIFEST, JSON.stringify(row) + '\n')
}

/**
 * Run every step of one scenario under one (locale, state) context.
 * `mockFor(state)` lets a step change backend behaviour mid-flow (e.g. make
 * the send endpoint return 500), which is how we exercise an error path.
 */
export async function runScenario(page, { scenario, locale, state, seed }) {
  if (seed) await seed(page, locale)

  for (let i = 0; i < scenario.steps.length; i++) {
    const step = scenario.steps[i]
    const stepId = `${scenario.id} · ${step.name} · ${locale} · ${state}`

    // 1. act
    await step.act(page, { state, installMocks, pwExpect })

    // small settle so the DOM reflects the action before we capture/judge
    await page.waitForTimeout(400)

    // 2. screenshot this step's resulting state
    const shot = `${SHOT_DIR}/${scenario.id}__${step.name}__${locale}__${state}.png`
    await page.screenshot({ path: shot, fullPage: true })

    // 3. deterministic assert (if the step defines one)
    let deterministic = 'pass'
    let assertError = ''
    if (step.assert) {
      try {
        await step.assert(page, pwExpect)
      } catch (err) {
        deterministic = 'fail'
        assertError = String(err?.message || err).split('\n')[0]
      }
    } else {
      // No deterministic check — this step is judged by the visual oracle
      // alone (against its explicit `expect`). Mark it so the report is honest.
      deterministic = 'visual-only'
    }

    // 4. emit a manifest row with the STEP-LEVEL expectation as the basis
    recordManifest({
      id: stepId,
      step: step.name,
      stepIndex: i,
      intent:
        step.expect?.[locale] || step.expect?.en || 'Step renders correctly.',
      screenshot: shot,
      locale,
      state,
      deterministic,
      assertError
    })
  }
}
