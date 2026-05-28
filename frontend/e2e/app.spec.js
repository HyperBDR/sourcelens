/**
 * E2E tests for the SourceLens app shell.
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

test.describe('App shell', () => {
  test('home redirects to dashboard or login', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')
    const url = page.url()
    expect(url).toMatch(/\/(dashboard|login)(\?|$)/)
  })
})

test.describe('Dashboard', () => {
  test.beforeEach(async ({ page }) => {
    const loggedIn = await tryLogin(page)
    if (!loggedIn) test.skip()
  })

  test('Dashboard page renders with hero and pillar sections', async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')

    await expect(page).toHaveURL(/\/dashboard/)
    // Hero title
    await expect(page.locator('h1').first()).toBeVisible({ timeout: 10000 })
    // Platform highlights section
    await expect(
      page.locator('text=/highlights|capabilities|highlightsTitle/i').first()
    ).toBeVisible({ timeout: 5000 })
  })

  test('Dashboard sidebar navigation is visible', async ({ page }) => {
    await page.goto('/dashboard')
    await page.waitForLoadState('networkidle')

    const sidebar = page.locator('nav, [class*="sidebar"]').first()
    await expect(sidebar).toBeVisible({ timeout: 5000 })
  })
})

test.describe('Settings', () => {
  test.beforeEach(async ({ page }) => {
    const loggedIn = await tryLogin(page)
    if (!loggedIn) test.skip()
  })

  test('Profile settings page loads', async ({ page }) => {
    await page.goto('/settings/profile')
    await page.waitForLoadState('networkidle')

    await expect(page).toHaveURL(/\/settings\/profile/)
    await expect(page.locator('h1, h2').first()).toBeVisible({ timeout: 10000 })
  })
})

test.describe('404 page', () => {
  test('unknown routes show 404 page', async ({ page }) => {
    await page.goto('/this-route-does-not-exist-xyz')
    await page.waitForLoadState('networkidle')
    // Should show 404 or redirect to /404
    const url = page.url()
    const bodyText = await page.locator('body').textContent()
    expect(
      url.includes('404') || bodyText.toLowerCase().includes('not found')
    ).toBeTruthy()
  })
})
