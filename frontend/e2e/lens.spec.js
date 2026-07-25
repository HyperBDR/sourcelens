/**
 * E2E smoke tests for Lens pages.
 */
import { test, expect } from '@playwright/test'

async function tryLogin(page) {
  const username = process.env.TEST_USERNAME || 'admin'
  const password = process.env.TEST_PASSWORD || 'adminpassword'

  await page.goto('/login')
  await page.waitForLoadState('networkidle')

  const response = await page.request.post('/api/v1/auth/login', {
    data: { username, password }
  })
  if (!response.ok()) return false

  const body = await response.json()
  const data = body?.data || body
  const access = data?.access || data?.access_token || data?.token
  const refresh = data?.refresh || data?.refresh_token
  if (!access) return false

  await page.addInitScript(
    ({ accessToken, refreshToken }) => {
      localStorage.setItem('access_token', accessToken)
      if (refreshToken) localStorage.setItem('refresh_token', refreshToken)
    },
    { accessToken: access, refreshToken: refresh }
  )
  return true
}

test.describe('Lens pages', () => {
  test.beforeEach(async ({ page }) => {
    const loggedIn = await tryLogin(page)
    expect(loggedIn).toBeTruthy()
  })

  test('assistants page renders', async ({ page }) => {
    await page.goto('/management/lens/assistants')
    await page.waitForLoadState('networkidle')

    await expect(page).toHaveURL(/\/management\/lens\/assistants/)
    await expect(page.locator('h1:visible, h2:visible').first()).toBeVisible({
      timeout: 10000
    })
  })

  test('admin resources page renders', async ({ page }) => {
    await page.goto('/management/lens/resources/credentials')
    await page.waitForLoadState('networkidle')

    await expect(page).toHaveURL(/\/management\/lens\/resources\/credentials/)
    await expect(page.locator('text=/Credentials|凭证/i').first()).toBeVisible({
      timeout: 10000
    })
  })
})
