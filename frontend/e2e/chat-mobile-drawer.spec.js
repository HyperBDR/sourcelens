import { expect, test } from '@playwright/test'

async function mockChat(page) {
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'test-token')
    localStorage.setItem('userLanguage', 'en')
  })

  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) {
      await route.continue()
      return
    }

    const payloads = {
      '/api/v1/auth/user': {
        username: 'tester',
        features: ['workspace'],
        permissions: []
      },
      '/api/lens/assistants/': [
        {
          uuid: 'assistant-1',
          slug: 'drawer-test',
          name: 'Drawer Test',
          status: 'active'
        }
      ],
      '/api/lens/shares/': [],
      '/api/lens/sessions/': [
        { uuid: 'session-1', title: 'First session' },
        { uuid: 'session-2', title: 'Second session' }
      ],
      '/api/lens/sessions/session-1/messages/': [],
      '/api/lens/sessions/session-2/messages/': [
        {
          uuid: 'message-2',
          role: 'assistant',
          content: 'Second session response',
          created_at: '2026-07-24T08:00:00Z'
        }
      ]
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: payloads[path] ?? [] })
    })
  })
}

async function sidebarBox(page) {
  return page.locator('.sidebar').evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return { x: rect.x, width: rect.width }
  })
}

test('mobile session drawer opens, selects sessions, and closes', async ({
  page
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockChat(page)
  await page.goto('/lens/assistants/drawer-test/chat')

  await expect.poll(() => sidebarBox(page)).toMatchObject({ x: -320 })

  await page.getByRole('button', { name: 'Recent' }).click()
  await expect(page.locator('.sidebar')).toHaveClass(/sidebar-open/)
  await expect.poll(() => sidebarBox(page)).toMatchObject({ x: 0, width: 320 })

  const secondSession = page
    .locator('.session-item')
    .filter({ hasText: 'Second session' })
  await expect(secondSession).toBeVisible()
  await secondSession.click()
  await expect(page).toHaveURL(/session=session-2/)
  await expect(page.getByText('Second session response')).toBeAttached()

  await page.locator('.sidebar').getByRole('button', { name: 'Close' }).click()
  await expect(page.locator('.sidebar')).not.toHaveClass(/sidebar-open/)
  await expect.poll(() => sidebarBox(page)).toMatchObject({ x: -320 })

  await page.getByRole('button', { name: 'Recent' }).click()
  await expect.poll(() => sidebarBox(page)).toMatchObject({ x: 0 })
  await page
    .locator('div.fixed.inset-0.z-20')
    .click({ position: { x: 380, y: 400 } })
  await expect(page.locator('.sidebar')).not.toHaveClass(/sidebar-open/)
  await expect.poll(() => sidebarBox(page)).toMatchObject({ x: -320 })
})

test('desktop sidebar still expands and collapses', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await mockChat(page)
  await page.goto('/lens/assistants/drawer-test/chat')

  await expect.poll(() => sidebarBox(page)).toMatchObject({ x: 0, width: 264 })
  await page.getByRole('button', { name: 'Collapse' }).click()
  await expect.poll(() => sidebarBox(page)).toMatchObject({ x: 0, width: 64 })
  await page.locator('.sidebar-collapse-btn[aria-label="Expand"]').click()
  await expect.poll(() => sidebarBox(page)).toMatchObject({ x: 0, width: 264 })
})
