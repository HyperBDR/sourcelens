/**
 * E2E tests for authentication: login form, validation, redirect guards.
 */
import { test, expect } from '@playwright/test'

/**
 * Attempt to log in using environment credentials or known test account.
 * Returns true if login succeeded (redirected away from /login).
 */
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
  await page.reload()
  await page.waitForLoadState('networkidle')
  return !page.url().includes('/login')
}

test.describe('Login page', () => {
  test('renders login form with all fields', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('networkidle')

    await expect(page.locator('input[name="email"]')).toBeVisible()
    await expect(
      page.getByRole('button', { name: /send code|发送验证码/i })
    ).toBeVisible()

    await page
      .getByRole('button', { name: /account password|账号密码/i })
      .click()
    await expect(page.locator('input[name="username"]')).toBeVisible()
    await expect(page.locator('input[name="password"]')).toBeVisible()
    await expect(page.locator('button[type="submit"]')).toBeVisible()
  })

  test('shows validation error when submitting empty form', async ({
    page
  }) => {
    await page.goto('/login')
    await page.waitForLoadState('networkidle')

    const email = page.locator('input[name="email"]')
    await page.click('button[type="submit"]')
    await expect(email).toHaveJSProperty('validity.valueMissing', true)
  })

  test('shows error for invalid credentials', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('networkidle')

    await page
      .getByRole('button', { name: /account password|账号密码/i })
      .click()
    await page.fill('input[name="username"]', 'wronguser')
    await page.fill('input[name="password"]', 'wrongpassword')
    await page.click('button[type="submit"]')
    await page.waitForLoadState('networkidle')

    // Should stay on login page
    expect(page.url()).toContain('/login')

    // Should show error message
    const errorMsg = page
      .locator('text=/error|incorrect|登录失败|invalid|错误/i')
      .first()
    await expect(errorMsg).toBeVisible({ timeout: 5000 })
  })

  test('login button is disabled while loading', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('networkidle')

    let releaseLogin
    const loginGate = new Promise((resolve) => {
      releaseLogin = resolve
    })
    await page.route('**/api/v1/auth/login', async (route) => {
      await loginGate
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Invalid credentials' })
      })
    })
    await page
      .getByRole('button', { name: /account password|账号密码/i })
      .click()
    await page.fill('input[name="username"]', 'admin')
    await page.fill('input[name="password"]', 'adminpassword')

    await page.click('button[type="submit"]')

    const btn = page.locator('button[type="submit"]').first()
    await expect(btn).toBeDisabled()
    releaseLogin()
    await expect(btn).toBeEnabled()
  })

  test('successful login redirects away from /login', async ({ page }) => {
    const loggedIn = await tryLogin(page)
    expect(loggedIn).toBeTruthy()
    expect(page.url()).not.toContain('/login')
  })
})

test.describe('Auth guards', () => {
  test('unauthenticated user is redirected to /login for protected routes', async ({
    page
  }) => {
    await page.addInitScript(() => localStorage.clear())
    await page.context().clearCookies()

    const protectedRoutes = [
      '/dashboard',
      '/management/users',
      '/management/task-management/list',
      '/settings/profile'
    ]

    for (const route of protectedRoutes) {
      await page.goto(route)
      await page.waitForLoadState('networkidle')
      expect(page.url()).toContain('/login')
    }
  })

  test('authenticated user is redirected away from /login', async ({
    page
  }) => {
    const loggedIn = await tryLogin(page)
    expect(loggedIn).toBeTruthy()
    await page.goto('/login')
    await page.waitForLoadState('networkidle')
    expect(page.url()).not.toContain('/login')
  })
})

test.describe('Language switcher', () => {
  test('language switcher is present on login page', async ({ page }) => {
    await page.goto('/login')
    await page.waitForLoadState('networkidle')
    const langSwitcher = page.locator('button[title]').first()
    await expect(langSwitcher).toBeVisible({ timeout: 5000 })
  })
})
