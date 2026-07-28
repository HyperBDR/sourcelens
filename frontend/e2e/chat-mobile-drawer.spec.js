import { expect, test } from '@playwright/test'

async function mockChat(page, messageDelays = {}) {
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
        { uuid: 'session-2', title: 'Second session' },
        { uuid: 'session-3', title: 'Third session' }
      ],
      '/api/lens/sessions/session-1/messages/': [],
      '/api/lens/sessions/session-2/messages/': [
        {
          uuid: 'message-2',
          role: 'assistant',
          content: 'Second session response',
          created_at: '2026-07-24T08:00:00Z'
        }
      ],
      '/api/lens/sessions/session-3/messages/': [
        {
          uuid: 'message-3',
          role: 'assistant',
          content: 'Third session response',
          created_at: '2026-07-24T08:01:00Z'
        }
      ]
    }

    if (messageDelays[path]) {
      await new Promise((resolve) => setTimeout(resolve, messageDelays[path]))
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

  const composer = page.locator('.composer-input')
  const initialComposerHeight = await composer.evaluate(
    (element) => element.getBoundingClientRect().height
  )
  await composer.fill('Session A draft\nsecond line\nthird line')
  await expect
    .poll(() =>
      composer.evaluate((element) => element.getBoundingClientRect().height)
    )
    .toBeGreaterThan(initialComposerHeight)

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
  await expect(composer).toHaveValue('')
  await expect
    .poll(() =>
      composer.evaluate((element) => element.getBoundingClientRect().height)
    )
    .toBe(initialComposerHeight)

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

test('stale session responses do not replace a newer session draft', async ({
  page
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockChat(page, {
    '/api/lens/sessions/session-2/messages/': 1000
  })
  await page.goto('/lens/assistants/drawer-test/chat')

  await page.getByRole('button', { name: 'Recent' }).click()
  const slowResponse = page.waitForResponse((response) =>
    response.url().includes('/sessions/session-2/messages/')
  )
  await page
    .locator('.session-item')
    .filter({ hasText: 'Second session' })
    .click()
  await page
    .locator('.session-item')
    .filter({ hasText: 'Third session' })
    .click()

  await expect(page).toHaveURL(/session=session-3/)
  await expect(page.getByText('Third session response')).toBeAttached()
  const composer = page.locator('.composer-input')
  await composer.fill('Session C draft\nsecond line\nthird line')
  const draftHeight = await composer.evaluate(
    (element) => element.getBoundingClientRect().height
  )

  const response = await slowResponse
  await response.finished()
  await page.evaluate(
    () =>
      new Promise((resolve) =>
        requestAnimationFrame(() => requestAnimationFrame(resolve))
      )
  )
  await expect(page).toHaveURL(/session=session-3/)
  await expect(page.getByText('Second session response')).not.toBeAttached()
  await expect(page.getByText('Third session response')).toBeAttached()
  await expect(composer).toHaveValue('Session C draft\nsecond line\nthird line')
  await expect
    .poll(() =>
      composer.evaluate((element) => element.getBoundingClientRect().height)
    )
    .toBe(draftHeight)
})
