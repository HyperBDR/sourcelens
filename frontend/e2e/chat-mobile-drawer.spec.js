import { expect, test } from '@playwright/test'

async function mockChat(
  page,
  messageDelays = {},
  language = 'en',
  assistantList = null
) {
  await page.addInitScript((selectedLanguage) => {
    localStorage.setItem('access_token', 'test-token')
    localStorage.setItem('userLanguage', selectedLanguage)
  }, language)

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
      '/api/lens/assistants/': assistantList || [
        {
          uuid: 'assistant-1',
          slug: 'drawer-test',
          name: 'Drawer Test',
          status: 'active',
          multimodal_model_ref: 'vision-model'
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
          run: 'run-2',
          feedback: 'positive',
          output_files: [
            {
              uuid: 'file-1',
              filename: 'report.pdf',
              byte_size: 1024,
              url: '/api/lens/output-files/file-1/content/'
            }
          ],
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

    if (path.endsWith('/attachments/')) {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({ data: { uuid: 'attachment-1' } })
      })
      return
    }

    if (path === '/api/lens/runs/run-2/share/') {
      await route.fulfill({
        contentType: 'application/json',
        body: JSON.stringify({
          data: {
            uuid: 'share-1',
            token: 'shared-token',
            title: 'Second session'
          }
        })
      })
      return
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

async function expectMinimumTouchTarget(locator) {
  const box = await locator.boundingBox()
  expect(box).not.toBeNull()
  expect(box.width).toBeGreaterThanOrEqual(44)
  expect(box.height).toBeGreaterThanOrEqual(44)
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

test('mobile header switches assistants without overflowing', async ({
  page
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockChat(page, {}, 'en', [
    {
      uuid: 'assistant-1',
      slug: 'drawer-test',
      name: 'Drawer Test',
      status: 'active'
    },
    {
      uuid: 'assistant-2',
      slug: 'mobile-switch',
      name: 'Mobile Switch',
      status: 'active'
    }
  ])
  await page.goto('/lens/assistants/drawer-test/chat')

  const switcher = page.getByRole('button', { name: 'Switch assistant' })
  await expect(switcher).toBeVisible()
  await expectMinimumTouchTarget(switcher)
  await switcher.click()

  const panel = page.locator('.assistant-switcher-panel')
  await expect(panel).toBeVisible()
  const panelBox = await panel.boundingBox()
  expect(panelBox).not.toBeNull()
  expect(panelBox.x).toBeGreaterThanOrEqual(0)
  expect(panelBox.x + panelBox.width).toBeLessThanOrEqual(390)

  await panel.getByRole('button', { name: /Mobile Switch/ }).click()
  await expect(page).toHaveURL('/lens/assistants/mobile-switch/chat')
  await expect(switcher).toContainText('Mobile Switch')
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

test.describe('touch input accessibility', () => {
  test.use({ hasTouch: true })

  test('chat actions stay visible, accessible, and touchable', async ({
    page
  }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await mockChat(page)
    await page.goto('/lens/assistants/drawer-test/chat')

    const recent = page.getByRole('button', { name: 'Recent' })
    await expectMinimumTouchTarget(recent)
    await recent.click()
    const firstSession = page
      .locator('.session-item')
      .filter({ hasText: 'First session' })
    const rename = firstSession.getByRole('button', { name: 'Rename' })
    const remove = firstSession.getByRole('button', {
      name: 'Delete session'
    })

    await expect(rename).toBeVisible()
    await expect(remove).toBeVisible()
    await expect(rename).toHaveCSS('opacity', '1')
    await expect(remove).toHaveCSS('opacity', '1')
    await expectMinimumTouchTarget(rename)
    await expectMinimumTouchTarget(remove)

    await remove.click()
    const confirmDelete = firstSession.getByRole('button', {
      name: 'Confirm delete'
    })
    const cancelDelete = firstSession.getByRole('button', { name: 'Cancel' })
    await expectMinimumTouchTarget(confirmDelete)
    await expectMinimumTouchTarget(cancelDelete)
    await cancelDelete.click()

    await page
      .locator('.session-item')
      .filter({ hasText: 'Second session' })
      .click()
    await page
      .locator('.sidebar')
      .getByRole('button', { name: 'Close' })
      .click()

    const copy = page.getByRole('button', { name: 'Copy' })
    const share = page.getByRole('button', { name: 'Share' })
    const retry = page.getByRole('button', { name: 'Retry' })
    const upload = page.getByRole('button', { name: 'Upload image' })
    const submit = page.getByRole('button', { name: 'Submit' })
    const preview = page.getByRole('button', { name: 'Preview' })
    const download = page.getByRole('button', { name: 'Download' })

    for (const action of [
      copy,
      share,
      retry,
      upload,
      submit,
      preview,
      download
    ]) {
      await expect(action).toBeVisible()
      await expectMinimumTouchTarget(action)
    }
    await expect(page.locator('.message-feedback-status')).toHaveCount(0)
    await expect(copy).toHaveAttribute('title', 'Copy')
    await expect(share).toHaveAttribute('title', 'Share')
    await expect(retry).toHaveAttribute('title', 'Retry')

    await page.locator('input[type="file"]').setInputFiles({
      name: 'mobile-test.png',
      mimeType: 'image/png',
      buffer: Buffer.from('mobile image')
    })
    const removeImage = page.getByRole('button', { name: 'Remove image' })
    const imagePreview = page.locator('.composer-thumb img')
    await expect(removeImage).toBeVisible()
    await expect(imagePreview).toHaveAttribute('src', /^blob:/)
    await expect(removeImage).toHaveAttribute('title', 'Remove image')
    await expectMinimumTouchTarget(removeImage)

    await share.click()
    const close = page.locator('.modal-close-btn')
    const createLink = page.getByRole('button', { name: 'Create link' })
    await expectMinimumTouchTarget(close)
    await expectMinimumTouchTarget(createLink)
    await createLink.click()
    await expectMinimumTouchTarget(
      page.getByRole('button', { name: 'Copy link' })
    )
    await expectMinimumTouchTarget(
      page.getByRole('button', { name: 'Stop sharing' })
    )
    await expectMinimumTouchTarget(page.getByRole('button', { name: 'Done' }))
  })

  test('icon action names are localized in Simplified Chinese', async ({
    page
  }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await mockChat(page, {}, 'zh-CN')
    await page.goto('/lens/assistants/drawer-test/chat')

    await page.getByRole('button', { name: '最近' }).click()
    await page
      .locator('.session-item')
      .filter({ hasText: 'Second session' })
      .click()

    const localizedActions = [
      ['复制', '复制'],
      ['分享', '分享'],
      ['重试', '重试'],
      ['上传图片', '上传图片'],
      ['预览', '预览'],
      ['下载', '下载']
    ]
    for (const [name, title] of localizedActions) {
      await expect(page.getByRole('button', { name })).toHaveAttribute(
        'title',
        title
      )
    }

    await page.locator('input[type="file"]').setInputFiles({
      name: 'mobile-test.png',
      mimeType: 'image/png',
      buffer: Buffer.from('mobile image')
    })
    await expect(
      page.getByRole('button', { name: '移除图片' })
    ).toHaveAttribute('title', '移除图片')
  })
})

test('desktop session actions retain compact hover behavior', async ({
  page
}) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await mockChat(page)
  await page.goto('/lens/assistants/drawer-test/chat')

  const firstSession = page
    .locator('.session-item')
    .filter({ hasText: 'First session' })
  const rename = firstSession.getByRole('button', { name: 'Rename' })
  const remove = firstSession.getByRole('button', { name: 'Delete session' })

  await expect(rename).toHaveCSS('opacity', '0')
  await expect(remove).toHaveCSS('opacity', '0')
  const renameBox = await rename.boundingBox()
  const removeBox = await remove.boundingBox()
  expect(renameBox).toMatchObject({ width: 24, height: 24 })
  expect(removeBox).toMatchObject({ width: 24, height: 24 })

  await firstSession.hover()
  await expect(rename).toHaveCSS('opacity', '1')
  await expect(remove).toHaveCSS('opacity', '1')
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
