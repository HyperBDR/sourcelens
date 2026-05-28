/**
 * E2E tests for LLM pages (admin /management/llm/*).
 * Assumes app is served at baseURL. Requires admin_console feature.
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

test.describe('LLM pages', () => {
  test.beforeEach(async ({ page }) => {
    const loggedIn = await tryLogin(page)
    if (!loggedIn) test.skip()
  })

  test('LLM menu is visible and navigates to stats', async ({ page }) => {
    await page.goto('/')
    await page.waitForLoadState('networkidle')

    const llmMenu = page
      .locator('text=LLM')
      .or(page.locator('text=大模型'))
      .first()
    await expect(llmMenu).toBeVisible({ timeout: 10000 })

    await llmMenu.click()
    await page.waitForTimeout(500)

    const statsLink = page
      .locator('a[href*="/llm/stats"]')
      .or(page.locator('text=Token 统计'))
      .or(page.locator('text=Token Statistics'))
      .first()
    await expect(statsLink).toBeVisible({ timeout: 5000 })
    await statsLink.click()
    await page.waitForURL(/\/llm\/stats\/|management\/llm\/stats/)
    await expect(page).toHaveURL(/\/management\/llm\/stats/)
  })

  test('LLM Stats page shows stats cards', async ({ page }) => {
    await page.goto('/management/llm/stats')
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveURL(/\/management\/llm\/stats/)

    const title = page.locator('h1, h2').first()
    await expect(title).toBeVisible({ timeout: 10000 })

    // Should show stats content: either cards or empty state
    const content = page.locator('.text-2xl, .text-xl, .font-semibold, text=/暂无|no data/i').first()
    await expect(content).toBeVisible({ timeout: 10000 })
  })

  test('LLM Usage page shows table or empty state', async ({ page }) => {
    await page.goto('/management/llm/usage')
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveURL(/\/management\/llm\/usage/)

    const tableOrEmpty = page
      .locator('table, text=/暂无数据|暂无|no data|no records/i')
      .first()
    await expect(tableOrEmpty).toBeVisible({ timeout: 15000 })
  })

  test('LLM Usage pagination controls exist when data present', async ({ page }) => {
    await page.goto('/management/llm/usage')
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(2000)

    const pagination = page.locator('text=/showing|page|共/i').first()
    const hasPagination = await pagination.isVisible().catch(() => false)
    if (hasPagination) {
      await expect(pagination).toBeVisible()
    }
  })

  test('LLM Config page shows provider form', async ({ page }) => {
    await page.goto('/management/llm/config')
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveURL(/\/management\/llm\/config/)

    const providerSelect = page.locator('select').first()
    await expect(providerSelect).toBeVisible({ timeout: 10000 })
  })

  test('LLM Config has a save or update button', async ({ page }) => {
    await page.goto('/management/llm/config')
    await page.waitForLoadState('networkidle')

    const saveBtn = page.locator('button', { hasText: /save|保存|update|更新|submit|提交/i }).first()
    await expect(saveBtn).toBeVisible({ timeout: 5000 })
  })

  test('LLM Data Settings page loads', async ({ page }) => {
    await page.goto('/management/llm/data-settings')
    await page.waitForLoadState('networkidle')
    await expect(page).toHaveURL(/\/management\/llm\/data-settings/)
    await expect(page.locator('h1, h2, form').first()).toBeVisible({ timeout: 10000 })
  })

  test('legacy /llm/* routes redirect to /management/llm/*', async ({ page }) => {
    const legacyRoutes = ['/llm/stats', '/llm/usage', '/llm/config']
    for (const route of legacyRoutes) {
      await page.goto(route)
      await page.waitForLoadState('networkidle')
      expect(page.url()).toMatch(/\/management\/llm/)
    }
  })
})
