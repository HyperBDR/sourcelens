import { expect, test } from '@playwright/test'

async function mockAdministration(page, themeMode = 'dark') {
  await page.addInitScript((mode) => {
    localStorage.setItem('access_token', 'appearance-theme-test')
    localStorage.setItem('userLanguage', 'en')
    localStorage.setItem('userThemeMode', mode)
    window.__observedThemes = []
    const recordTheme = () => {
      window.__observedThemes.push(document.documentElement.dataset.theme)
    }
    new MutationObserver(recordTheme).observe(document.documentElement, {
      attributeFilter: ['data-theme'],
      attributes: true
    })
  }, themeMode)

  await page.route('**://*/api/**', async (route) => {
    const { pathname } = new URL(route.request().url())
    let data = []

    if (pathname === '/api/v1/auth/user') {
      data = {
        id: 1,
        username: 'admin',
        is_staff: true,
        is_superuser: true,
        features: ['admin_console', 'workspace'],
        permissions: []
      }
    } else if (pathname === '/api/v1/management/users/') {
      data = { count: 0, results: [] }
    } else if (pathname === '/api/v1/management/groups/') {
      data = { count: 0, results: [] }
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data })
    })
  })
}

test('administration stays light and leaving restores the saved theme', async ({
  page
}) => {
  await mockAdministration(page)
  await page.goto('/management/users')

  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  expect(await page.evaluate(() => localStorage.getItem('userThemeMode'))).toBe(
    'dark'
  )
  expect(await page.evaluate(() => window.__observedThemes)).not.toContain(
    'dark'
  )

  await page.evaluate(() => localStorage.removeItem('access_token'))
  await page.goto('/login')

  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
})

test('system mode follows the browser color scheme', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('userLanguage', 'en')
    localStorage.setItem('userThemeMode', 'system')
  })
  await page.emulateMedia({ colorScheme: 'dark' })
  await page.goto('/login')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')

  await page.emulateMedia({ colorScheme: 'light' })
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
})

test('scheduled mode changes at the local boundaries', async ({ page }) => {
  await page.clock.install({ time: new Date(2026, 7, 4, 20, 0, 0) })
  await page.addInitScript(() => {
    localStorage.setItem('userLanguage', 'en')
    localStorage.setItem('userThemeMode', 'scheduled')
  })
  await page.goto('/login')
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')

  await page.clock.setFixedTime(new Date(2026, 7, 5, 7, 0, 0))
  await page.reload()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
})

test('user-facing logo keeps its source and geometry across themes', async ({
  page
}) => {
  await page.addInitScript(() => {
    localStorage.setItem('userLanguage', 'en')
    if (!localStorage.getItem('userThemeMode')) {
      localStorage.setItem('userThemeMode', 'light')
    }
  })
  await page.goto('/login')

  const logo = page.getByRole('img', { name: 'SourceLens' })
  await expect(logo).toHaveCount(1)
  const lightSource = await logo.getAttribute('src')
  const lightBox = await logo.boundingBox()

  await page.evaluate(() => {
    localStorage.setItem('userThemeMode', 'dark')
  })
  await page.reload()

  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  const darkSource = await logo.getAttribute('src')
  expect(darkSource).not.toBe(lightSource)
  expect(darkSource).toContain('logo_dark_transparent.png')
  expect(await logo.boundingBox()).toEqual(lightBox)
})

test('user-facing wordmark switches source without moving', async ({
  page
}) => {
  await page.addInitScript(() => {
    localStorage.setItem('userLanguage', 'en')
    if (!localStorage.getItem('userThemeMode')) {
      localStorage.setItem('userThemeMode', 'light')
    }
  })
  await page.route(
    '**/api/lens/public/assistants/appearance-wordmark/qa/**',
    async (route) => {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            assistant: {
              name: 'Appearance Wordmark',
              slug: 'appearance-wordmark'
            },
            next_offset: null,
            results: [],
            total: 0
          }
        })
      })
    }
  )
  await page.goto('/lens/assistants/appearance-wordmark/qa')

  const wordmark = page.getByRole('img', { name: 'SourceLens' })
  await expect(wordmark).toHaveCount(1)
  await expect(wordmark).toHaveAttribute(
    'src',
    /logo_with_text_transparent\.png/
  )
  const lightSource = await wordmark.getAttribute('src')
  const lightBox = await wordmark.boundingBox()

  await page.evaluate(() => {
    localStorage.setItem('userThemeMode', 'dark')
  })
  await page.reload()

  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  const darkSource = await wordmark.getAttribute('src')
  expect(darkSource).not.toBe(lightSource)
  expect(darkSource).toContain('logo_with_text_dark_transparent.png')
  expect(await wordmark.boundingBox()).toEqual(lightBox)
})
