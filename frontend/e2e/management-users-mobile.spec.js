import { expect, test } from '@playwright/test'

async function mockManagement(page) {
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'e2e-management-mobile')
    localStorage.setItem('userLanguage', 'en')
  })

  await page.route('**://*/api/**', async (route) => {
    const { pathname } = new URL(route.request().url())
    let data = []

    if (pathname === '/api/v1/auth/user') {
      data = {
        id: 1,
        username: 'admin',
        is_staff: true,
        is_superuser: true,
        permissions: []
      }
    } else if (pathname === '/api/v1/management/users/') {
      data = {
        count: 3,
        results: [
          {
            id: 1,
            username: 'admin',
            display_name: 'admin',
            email: 'admin',
            is_active: true,
            is_staff: true,
            groups: []
          },
          {
            id: 2,
            username: 'operator',
            display_name: 'Operations Owner',
            email: 'operator@example.com',
            is_active: true,
            is_staff: true,
            groups: []
          },
          {
            id: 3,
            username: `long-${'username-'.repeat(30)}end`,
            display_name: '',
            email: 'long-user@example.com',
            is_active: true,
            is_staff: false,
            groups: []
          }
        ]
      }
    } else if (pathname === '/api/v1/management/groups/') {
      data = { count: 0, results: [] }
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data })
    })
  })
}

test('user filters keep distinct rows and usable widths on mobile', async ({
  page
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockManagement(page)
  await page.goto('/management/users')

  const username = page.getByTestId('username-filter-input')
  const email = page.getByTestId('email-filter-input')
  const search = page.getByTestId('user-filter-submit')
  const reset = page.getByTestId('user-filter-reset')

  await expect(username).toBeVisible()
  await expect(email).toBeVisible()

  const [usernameBox, emailBox, searchBox, resetBox] = await Promise.all([
    username.boundingBox(),
    email.boundingBox(),
    search.boundingBox(),
    reset.boundingBox()
  ])

  for (const box of [usernameBox, emailBox, searchBox, resetBox]) {
    expect(box).not.toBeNull()
    expect(box.width).toBeGreaterThanOrEqual(120)
    expect(box.height).toBeGreaterThanOrEqual(44)
  }
  expect(usernameBox.y).toBe(emailBox.y)
  expect(searchBox.y).toBe(resetBox.y)
  expect(searchBox.y).toBeGreaterThan(usernameBox.y + usernameBox.height)
})

test('user identities stay distinct and row actions remain reachable', async ({
  page
}) => {
  await page.setViewportSize({ width: 1512, height: 945 })
  await mockManagement(page)
  await page.goto('/management/users')

  const identities = page.getByTestId('user-identity')
  await expect(identities).toHaveCount(3)
  await expect(identities.nth(0).getByTestId('secondary-identity')).toHaveCount(
    0
  )
  await expect(identities.nth(1).getByTestId('secondary-identity')).toHaveText(
    'Operations Owner'
  )
  await expect(page.getByTestId('user-email').nth(0)).toHaveText('—')
  await expect(page.getByTestId('user-email').nth(1)).toHaveText(
    'operator@example.com'
  )

  const longUsername = `long-${'username-'.repeat(30)}end`
  await expect(
    identities.nth(2).getByTestId('user-detail-trigger')
  ).toHaveAttribute('title', longUsername)

  const table = page.getByTestId('user-table-scroll')
  const actions = page.getByTestId('user-actions').first()
  const scrollWidth = await table.evaluate((element) => element.scrollWidth)
  const actionsBox = await actions.boundingBox()

  expect(scrollWidth).toBeLessThan(1300)
  expect(actionsBox).not.toBeNull()
  expect(actionsBox.x + actionsBox.width).toBeLessThanOrEqual(1512)
})

for (const width of [320, 768, 1280]) {
  test(`user table keeps columns reachable at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 })
    await mockManagement(page)
    await page.goto('/management/users')

    const table = page.getByTestId('user-table-scroll')
    const actions = page.getByTestId('user-actions').first()
    await expect(actions).toBeVisible()

    const overflow = await table.evaluate((element) => ({
      clientWidth: element.clientWidth,
      overflowX: getComputedStyle(element).overflowX,
      scrollWidth: element.scrollWidth
    }))

    expect(overflow.overflowX).toBe('auto')
    expect(overflow.scrollWidth).toBeGreaterThan(overflow.clientWidth)

    await table.evaluate((element) => {
      element.scrollLeft = element.scrollWidth
    })
    const actionsBox = await actions.boundingBox()
    expect(actionsBox).not.toBeNull()
    expect(actionsBox.x + actionsBox.width).toBeLessThanOrEqual(width)
  })
}
