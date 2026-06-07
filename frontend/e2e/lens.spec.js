/**
 * E2E smoke tests for Lens pages.
 */
import { test, expect } from '@playwright/test'

async function tryLogin(page) {
  const username = process.env.TEST_USERNAME || 'admin'
  const password = process.env.TEST_PASSWORD || 'admin'

  await page.goto('/login')
  await page.waitForLoadState('networkidle')

  const loginForm = page.locator('form').first()
  const formVisible = await loginForm.isVisible().catch(() => false)
  if (!formVisible) return false

  await page.fill('input[name="username"]', username)
  await page.fill('input[name="password"]', password)
  await page.click('button[type="submit"]')
  await page.waitForLoadState('networkidle')
  return !page.url().includes('/login')
}

test.describe('Lens pages', () => {
  test.beforeEach(async ({ page }) => {
    const loggedIn = await tryLogin(page)
    if (!loggedIn) test.skip()
  })

  test('assistants page renders', async ({ page }) => {
    await page.goto('/lens/assistants')
    await page.waitForLoadState('networkidle')

    await expect(page).toHaveURL(/\/lens\/assistants/)
    await expect(page.locator('h1, h2').first()).toBeVisible({
      timeout: 10000
    })
  })

  test('admin resources page renders', async ({ page }) => {
    await page.goto('/lens/admin/resources')
    await page.waitForLoadState('networkidle')

    await expect(page).toHaveURL(/\/lens\/admin\/resources/)
    await expect(
      page.locator('text=/Lens Admin|资源与调度/i').first()
    ).toBeVisible({
      timeout: 10000
    })
  })
})
