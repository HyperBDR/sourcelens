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
