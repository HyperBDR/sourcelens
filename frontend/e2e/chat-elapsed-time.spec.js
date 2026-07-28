import { expect, test } from '@playwright/test'

function elapsedTextToSeconds(text) {
  const minutes = text.match(/(\d+)m/)?.[1] ?? 0
  const seconds = text.match(/(\d+)s/)?.[1] ?? 0
  return Number(minutes) * 60 + Number(seconds)
}

async function mockActiveRunChat(page) {
  const createdAt = new Date(Date.now() - 75000).toISOString()

  await page.addInitScript(() => {
    localStorage.setItem('access_token', 'test-token')
  })

  await page.route('**/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname
    if (!path.startsWith('/api/')) {
      await route.continue()
      return
    }
    if (path === '/api/lens/runs/run-1/stream/') {
      await route.fulfill({
        contentType: 'text/event-stream',
        body: 'data: {"type":"sync","status":"running","steps":[]}\n\n'
      })
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
          slug: 'elapsed-test',
          name: 'Elapsed Test',
          status: 'active'
        }
      ],
      '/api/lens/shares/': [],
      '/api/lens/sessions/': [
        { uuid: 'session-1', title: 'Active session' },
        { uuid: 'session-2', title: 'Idle session' }
      ],
      '/api/lens/sessions/session-1/messages/': [
        {
          uuid: 'question-1',
          role: 'user',
          content: 'Keep working',
          run: 'run-1',
          created_at: createdAt
        },
        {
          uuid: 'answer-1',
          role: 'assistant',
          content: '',
          run: 'run-1',
          created_at: createdAt
        }
      ],
      '/api/lens/sessions/session-2/messages/': [],
      '/api/lens/runs/run-1/': {
        uuid: 'run-1',
        status: 'running',
        created_at: createdAt,
        steps: []
      }
    }

    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({ data: payloads[path] ?? [] })
    })
  })
}

async function visibleElapsedSeconds(page) {
  const elapsed = page.locator('.thinking-elapsed')
  await expect(elapsed).toBeVisible()
  return elapsedTextToSeconds(await elapsed.innerText())
}

async function expectRestoredElapsed(page) {
  const elapsed = await visibleElapsedSeconds(page)
  expect(elapsed).toBeGreaterThanOrEqual(75)
  expect(elapsed).toBeLessThanOrEqual(90)
}

test('restores elapsed time after reload and session re-entry', async ({
  page
}) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await mockActiveRunChat(page)
  await page.goto('/lens/assistants/elapsed-test/chat')

  await expectRestoredElapsed(page)

  await page.reload()
  await expectRestoredElapsed(page)

  await page.getByText('Idle session', { exact: true }).click()
  await expect(page.locator('.thinking-elapsed')).toHaveCount(0)

  await page.getByText('Active session', { exact: true }).click()
  await expectRestoredElapsed(page)
})
