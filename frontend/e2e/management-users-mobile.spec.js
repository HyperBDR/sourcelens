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
        count: 1,
        results: [
          {
            id: 1,
            username: 'admin',
            email: 'admin@example.com',
            is_active: true,
            is_staff: true,
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
