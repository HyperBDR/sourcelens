import { expect, test } from '@playwright/test'

import { asRole } from './helpers.js'

const MOBILE_VIEWPORT = { width: 390, height: 844 }

async function expectSidebarX(sidebar, expectedX) {
  await expect
    .poll(async () => Math.round((await sidebar.boundingBox()).x))
    .toBe(expectedX)
}

test.describe('Admin mobile navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(MOBILE_VIEWPORT)
    await asRole(page, 'admin')
    await page.addInitScript(() => {
      window.localStorage.setItem('userLanguage', 'zh-CN')
    })
    await page.goto('/management/users')
  })

  test('opens, navigates, and closes the sidebar', async ({ page }) => {
    const sidebar = page.locator('#admin-sidebar')
    const openButton = page.locator('button[aria-controls="admin-sidebar"]')

    await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN')
    await expect(openButton).toHaveAccessibleName('展开 SourceLens Admin')
    await expect(openButton).toHaveAttribute('aria-expanded', 'false')
    await expectSidebarX(sidebar, -256)

    await openButton.click()

    await expect(openButton).toHaveAttribute('aria-expanded', 'true')
    await expect(page.locator('.layout-admin-overlay')).toBeVisible()
    await expectSidebarX(sidebar, 0)

    await sidebar.locator('a[href="/management/groups"]').click()

    await expect(page).toHaveURL(/\/management\/groups$/)
    const navigatedSidebar = page.locator('#admin-sidebar')
    const navigatedOpenButton = page.locator(
      'button[aria-controls="admin-sidebar"]'
    )
    await expectSidebarX(navigatedSidebar, -256)
    await expect(navigatedOpenButton).toHaveAttribute('aria-expanded', 'false')
    await expect(page.locator('.layout-admin-overlay')).toBeHidden()

    await navigatedOpenButton.click()
    const closeButton = page.locator(
      '#admin-sidebar button[aria-label="关闭 SourceLens Admin"]'
    )
    await expect(closeButton).toHaveAccessibleName('关闭 SourceLens Admin')
    await closeButton.click()
    await expectSidebarX(navigatedSidebar, -256)
    await expect(navigatedOpenButton).toHaveAttribute('aria-expanded', 'false')
    await expect(page.locator('.layout-admin-overlay')).toBeHidden()

    await navigatedOpenButton.click()
    await page
      .locator('.layout-admin-overlay')
      .click({ position: { x: 300, y: 400 } })
    await expectSidebarX(navigatedSidebar, -256)
    await expect(navigatedOpenButton).toHaveAttribute('aria-expanded', 'false')
    await expect(page.locator('.layout-admin-overlay')).toBeHidden()
  })

  test('keeps the desktop sidebar visible', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 })

    await expect(
      page.locator('button[aria-controls="admin-sidebar"]')
    ).toBeHidden()
    await expectSidebarX(page.locator('#admin-sidebar'), 0)
  })
})
