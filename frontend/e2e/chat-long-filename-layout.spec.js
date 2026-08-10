import { expect, test } from '@playwright/test'

const longFilenames = [
  'Git面试高频问题+简洁答案（适配Word）.pdf',
  'Git面试高频问题+简洁答案（适配Word）.docx',
  'Git面试高频问题+简洁答案（适配Word）.pptx',
  'Git面试高频问题+简洁答案（适配Word）.xlsx'
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
          slug: 'long-filename-test',
          name: 'Long Filename Test',
          status: 'active'
        }
      ],
      '/api/lens/shares/': [],
      '/api/lens/sessions/': [
        {
          uuid: 'session-1',
          title: 'Long filename test',
          status: 'active'
        }
      ],
      '/api/lens/sessions/session-1/messages/': [
        {
          uuid: 'message-1',
          role: 'user',
          content: '解析一下这个文档',
          attachments: longFilenames.map((filename, index) => ({
            uuid: `attachment-${index + 1}`,
            kind: 'document',
            original_name: filename,
            byte_size: 331300
          })),
          created_at: '2026-08-10T03:32:00Z'
        }
      ]
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: payloads[path] ?? [] })
    })
  })
}

test('keeps a long document filename inside the mobile message card', async ({
  page
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockChat(page)
  await page.goto('/lens/assistants/long-filename-test/chat?session=session-1')

  const cards = page.locator('.message-document-card')
  await expect(cards).toHaveCount(longFilenames.length)

  for (const [index, extension] of [
    '.pdf',
    '.docx',
    '.pptx',
    '.xlsx'
  ].entries()) {
    const card = cards.nth(index)
    await expect(card.locator('strong')).toContainText(extension)
    await expect(card.locator('strong')).toContainText('...')
  }

  const bounds = await cards.evaluateAll((elements) =>
    elements.map((element) => {
      const parent = element.closest('.message-card')
      const cardBox = element.getBoundingClientRect()
      const parentBox = parent.getBoundingClientRect()
      return {
        cardLeft: cardBox.left,
        cardRight: cardBox.right,
        parentLeft: parentBox.left,
        parentRight: parentBox.right,
        bodyWidth: document.body.scrollWidth,
        viewportWidth: window.innerWidth
      }
    })
  )

  for (const bound of bounds) {
    expect(bound.cardLeft).toBeGreaterThanOrEqual(bound.parentLeft)
    expect(bound.cardRight).toBeLessThanOrEqual(bound.parentRight)
    expect(bound.bodyWidth).toBeLessThanOrEqual(bound.viewportWidth)
  }
})
