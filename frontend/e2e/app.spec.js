/**
 * E2E tests for the SourceLens app shell.
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

test.describe('App shell', () => {
  test('home redirects to dashboard or login', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const url = page.url()
    expect(url).toMatch(/\/(dashboard|login)(\?|$)/)
  })
})

test.describe('Authenticated landing', () => {
  test.beforeEach(async ({ page }) => {
    const loggedIn = await tryLogin(page)
    expect(loggedIn).toBeTruthy()
  })

  test('dashboard route resolves to an available workspace', async ({
    page
  }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')

    await expect(page).toHaveURL(/\/lens\/assistants\/[^/]+\/chat/)
    await expect(page.locator('.composer-input')).toBeVisible({
      timeout: 10000
    })
  })

  test('workspace sidebar navigation is visible', async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')

    await expect(page).toHaveURL(/\/lens\/assistants\/[^/]+\/chat/)
    const sidebar = page.locator('nav, [class*="sidebar"]').first()
    await expect(sidebar).toBeVisible({ timeout: 5000 })
  })
})

test.describe('Settings', () => {
  test.beforeEach(async ({ page }) => {
    const loggedIn = await tryLogin(page)
    expect(loggedIn).toBeTruthy()
  })

  test('legacy profile settings route resolves to the user landing', async ({
    page
  }) => {
    await page.goto('/settings/profile')
    await page.waitForLoadState('networkidle')

    await expect(page).toHaveURL(/\/lens\/assistants\/[^/]+\/chat/)
    await expect(
      page
        .locator('.composer-input')
        .or(page.getByRole('heading', { name: /Welcome to SourceLens|欢迎/i }))
        .first()
    ).toBeVisible({ timeout: 10000 })
  })
})

test.describe('404 page', () => {
  test('unknown routes show 404 page', async ({ page }) => {
    await page.goto('/this-route-does-not-exist-xyz')
    await page.waitForLoadState('networkidle')
    await expect(page.getByRole('heading', { name: '404' })).toBeVisible()
  })
})
