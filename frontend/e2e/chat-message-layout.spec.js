import { expect, test } from '@playwright/test'

const viewports = [
  { name: 'desktop', width: 1280, height: 800 },
  { name: 'mobile', width: 390, height: 844 }
]

const messages = [
  {
    uuid: 'short-message',
    role: 'user',
    content: 'Short question',
    created_at: '2026-07-16T09:00:00Z'
  },
  {
    uuid: 'long-message',
    role: 'user',
    content:
      'First paragraph with a long unbroken value: ' +
      'x'.repeat(120) +
      '\n\nSecond paragraph remains inside the same message card.',
    created_at: '2026-07-16T09:01:00Z'
  }
]

async function mockChat(page) {
  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'test-token')
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
          slug: 'layout-test',
          name: 'Layout Test',
          status: 'active'
        }
      ],
      '/api/lens/shares/': [],
      '/api/lens/sessions/': [
        {
          uuid: 'session-1',
          title: 'Layout test'
        }
      ],
      '/api/lens/sessions/session-1/messages/': messages
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: payloads[path] ?? [] })
    })
  })
}

for (const viewport of viewports) {
  test(`user messages use a contained, left-aligned layout on ${viewport.name}`, async ({
    page
  }) => {
    await page.setViewportSize(viewport)
    await mockChat(page)
    await page.goto('/lens/assistants/layout-test/chat')

    const cards = page.locator('.message-card.user')
    await expect(cards).toHaveCount(2)

    const shortCard = cards.nth(0)
    const longCard = cards.nth(1)
    const shortStyles = await shortCard.evaluate((element) => {
      const styles = getComputedStyle(element)
      return {
        backgroundColor: styles.backgroundColor,
        padding: styles.padding,
        textAlign: styles.textAlign
      }
    })
    const longStyles = await longCard.evaluate((element) => {
      const styles = getComputedStyle(element)
      return {
        backgroundColor: styles.backgroundColor,
        padding: styles.padding,
        textAlign: styles.textAlign,
        whiteSpace: getComputedStyle(element.querySelector('.message-text'))
          .whiteSpace
      }
    })

    expect(shortStyles.backgroundColor).not.toBe('rgba(0, 0, 0, 0)')
    expect(shortStyles.padding).not.toBe('0px')
    expect(shortStyles.textAlign).toBe('left')
    expect(longStyles).toMatchObject(shortStyles)
    expect(longStyles.whiteSpace).toBe('pre-wrap')

    const fitsContainer = await longCard.evaluate(
      (element) => element.scrollWidth <= element.clientWidth
    )
    expect(fitsContainer).toBe(true)

    const box = await longCard.boundingBox()
    expect(box.x).toBeGreaterThanOrEqual(0)
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width)
  })
}
