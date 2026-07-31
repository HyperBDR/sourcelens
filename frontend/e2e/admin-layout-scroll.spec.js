import { expect, test } from '@playwright/test'

const VIEWPORTS = [
  { width: 1512, height: 945 },
  { width: 1920, height: 1080 }
]

function assistant(index) {
  return {
    uuid: `assistant-${index}`,
    name: `Assistant ${index}`,
    slug: `assistant-${index}-with-a-long-display-name`,
    lensnode: 'local-development-lensnode',
    selected_task: 'knowledge_qa',
    selected_dirs: [{ path: '/workspace/default' }],
    status: 'active',
    visibility: 'public',
    skill_summary: { enabled: 1 },
    mcp_summary: { enabled: 1 }
  }
}

async function mockAdminApis(page) {
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'e2e-admin-layout')
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
    } else if (pathname === '/api/lens/assistants/') {
      data = Array.from({ length: 6 }, (_, index) => assistant(index + 1))
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data })
    })
  })
}

for (const viewport of VIEWPORTS) {
  test(`admin layout contains scrolling at ${viewport.width}x${viewport.height}`, async ({
    page
  }) => {
    await page.setViewportSize(viewport)
    await mockAdminApis(page)
    await page.goto('/management/lens/assistants')
    await expect(
      page.getByRole('heading', { name: 'Assistants', exact: true })
    ).toBeVisible()
    await expect(page.locator('tbody tr')).toHaveCount(6)

    const layout = await page.evaluate(() => {
      const root = document.scrollingElement
      const shell = document.querySelector('.layout-admin')
      const main = shell.querySelector('main')
      const shellRect = shell.getBoundingClientRect()

      return {
        rootClientHeight: root.clientHeight,
        rootScrollHeight: root.scrollHeight,
        shellTop: shellRect.top,
        shellBottom: shellRect.bottom,
        viewportHeight: window.innerHeight,
        mainOverflowY: getComputedStyle(main).overflowY
      }
    })

    expect(layout.rootScrollHeight).toBe(layout.rootClientHeight)
    expect(layout.shellTop).toBe(0)
    expect(layout.shellBottom).toBe(layout.viewportHeight)
    expect(layout.mainOverflowY).toBe('auto')
  })
}

test('admin sidebar reveals a deep direct link with minimal scrolling', async ({
  page
}) => {
  await page.setViewportSize({ width: 1280, height: 600 })
  await mockAdminApis(page)
  await page.goto('/management/notifier/settings')

  const navigation = page.locator('#admin-sidebar nav')
  const activeItem = navigation.locator('.admin-nav-item-active')
  await expect(activeItem).toHaveAttribute(
    'href',
    '/management/notifier/settings'
  )

  const position = await navigation.evaluate((element) => {
    const active = element.querySelector('.admin-nav-item-active')
    const containerRect = element.getBoundingClientRect()
    const activeRect = active.getBoundingClientRect()
    return {
      activeBottom: activeRect.bottom,
      activeTop: activeRect.top,
      containerBottom: containerRect.bottom,
      containerTop: containerRect.top,
      scrollTop: element.scrollTop
    }
  })

  expect(position.scrollTop).toBeGreaterThan(0)
  expect(position.activeTop).toBeGreaterThanOrEqual(position.containerTop)
  expect(position.activeBottom).toBeLessThanOrEqual(position.containerBottom)
})

test('admin sidebar hides only its scrollbar and keeps native scrolling', async ({
  page
}) => {
  await page.setViewportSize({ width: 1280, height: 600 })
  await mockAdminApis(page)
  await page.goto('/management/users')

  const navigation = page.locator('#admin-sidebar nav')
  await expect(navigation).toBeVisible()
  const styles = await navigation.evaluate((nav) => {
    const main = document.querySelector('.layout-admin main')
    const navStyle = getComputedStyle(nav)
    const navScrollbarStyle = getComputedStyle(nav, '::-webkit-scrollbar')
    const mainStyle = getComputedStyle(main)
    return {
      mainOverflowY: mainStyle.overflowY,
      mainScrollbarWidth: mainStyle.scrollbarWidth,
      navOverflowY: navStyle.overflowY,
      navScrollbarDisplay: navScrollbarStyle.display,
      navScrollbarWidth: navStyle.scrollbarWidth,
      navWebkitScrollbarWidth: navScrollbarStyle.width
    }
  })

  expect(styles.navOverflowY).toBe('auto')
  expect(styles.navScrollbarWidth).toBe('none')
  expect(
    styles.navScrollbarDisplay === 'none' ||
      styles.navWebkitScrollbarWidth === '0px'
  ).toBe(true)
  expect(styles.mainOverflowY).toBe('auto')
  expect(styles.mainScrollbarWidth).not.toBe('none')

  await navigation.focus()
  await expect(navigation).toBeFocused()
  await page.keyboard.press('PageDown')
  await expect
    .poll(() => navigation.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0)

  const afterPageDown = await navigation.evaluate(
    (element) => element.scrollTop
  )
  await page.keyboard.press('ArrowDown')
  await expect
    .poll(() => navigation.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(afterPageDown)

  const afterArrowDown = await navigation.evaluate(
    (element) => element.scrollTop
  )
  await page.keyboard.press('ArrowUp')
  await expect
    .poll(() => navigation.evaluate((element) => element.scrollTop))
    .toBeLessThan(afterArrowDown)

  const afterArrowUp = await navigation.evaluate((element) => element.scrollTop)
  await page.keyboard.press('PageUp')
  await expect
    .poll(() => navigation.evaluate((element) => element.scrollTop))
    .toBeLessThan(afterArrowUp)

  await navigation.evaluate((element) => {
    element.scrollTop = 0
  })
  await navigation.hover()
  await page.mouse.wheel(0, 240)
  await expect
    .poll(() => navigation.evaluate((element) => element.scrollTop))
    .toBeGreaterThan(0)
})

test('admin sidebar preserves position across navigation and group toggles', async ({
  page
}) => {
  await page.setViewportSize({ width: 1280, height: 600 })
  await mockAdminApis(page)
  await page.goto('/management/notifier/stats')

  const navigation = page.locator('#admin-sidebar nav')
  await navigation.evaluate((element) => {
    element.scrollTop = element.scrollHeight - element.clientHeight
    element.dispatchEvent(new Event('scroll'))
  })
  const beforeNavigation = await navigation.evaluate(
    (element) => element.scrollTop
  )

  await navigation.locator('a[href="/management/notifier/records"]').click()
  await expect(page).toHaveURL(/\/management\/notifier\/records$/)
  await expect(
    navigation.locator('a[href="/management/notifier/records"]')
  ).toHaveClass(/admin-nav-item-active/)
  const afterNavigation = await navigation.evaluate(
    (element) => element.scrollTop
  )

  expect(afterNavigation).toBe(beforeNavigation)

  const notificationToggle = navigation.getByRole('button', {
    name: 'Notifications',
    exact: true
  })
  await notificationToggle.click()
  const afterCollapse = await navigation.evaluate(
    (element) => element.scrollTop
  )
  expect(afterCollapse).toBeGreaterThan(0)

  await notificationToggle.click()
  await expect(
    navigation.locator('a[href="/management/notifier/records"]')
  ).toBeVisible()
  await page.waitForTimeout(250)

  const activePosition = await navigation.evaluate((element) => {
    const active = element.querySelector('.admin-nav-item-active')
    const containerRect = element.getBoundingClientRect()
    const activeRect = active.getBoundingClientRect()
    return {
      activeBottom: activeRect.bottom,
      activeTop: activeRect.top,
      containerBottom: containerRect.bottom,
      containerTop: containerRect.top
    }
  })
  expect(activePosition.activeTop).toBeGreaterThanOrEqual(
    activePosition.containerTop - 1
  )
  expect(activePosition.activeBottom).toBeLessThanOrEqual(
    activePosition.containerBottom + 1
  )
})

test('admin user menu exposes a full-width settings hit area', async ({
  page
}) => {
  await page.setViewportSize({ width: 1512, height: 945 })
  await mockAdminApis(page)
  await page.goto('/management/users')

  const header = page.locator('header')
  await header.getByRole('button', { name: /admin/i }).click()

  const settingsBox = await header
    .getByRole('button', { name: 'Settings', exact: true })
    .boundingBox()
  const logoutBox = await header
    .getByRole('button', { name: 'Logout', exact: true })
    .boundingBox()

  expect(settingsBox).not.toBeNull()
  expect(logoutBox).not.toBeNull()
  expect(settingsBox.width).toBeGreaterThanOrEqual(logoutBox.width * 0.98)
  expect(Math.abs(settingsBox.x - logoutBox.x)).toBeLessThanOrEqual(3)
  expect(
    Math.abs(
      settingsBox.x + settingsBox.width - (logoutBox.x + logoutBox.width)
    )
  ).toBeLessThanOrEqual(3)
})
