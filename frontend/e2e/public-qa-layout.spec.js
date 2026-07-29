import { expect, test } from '@playwright/test'

const SHARE_TOKEN = 'e2e-wide-table'
const INPUT_UUID = '11111111-1111-4111-8111-111111111111'
const HTML_UUID = '22222222-2222-4222-8222-222222222222'
const BROKEN_UUID = '33333333-3333-4333-8333-333333333333'
const ARCHIVE_UUID = '44444444-4444-4444-8444-444444444444'
const TABLE_MARKDOWN = `
| Environment | Region | Provider | Instance type | Operating system | Database | Cache | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Production | Asia Pacific | OnePro Cloud | Memory optimized | Ubuntu 24.04 LTS | PostgreSQL 16 | Redis 7 | Healthy |
`

test('wide shared Q&A tables scroll without widening the page', async ({
  page
}) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route(`**/api/lens/public/qa/${SHARE_TOKEN}/`, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          title: 'Wide table layout',
          question: 'Wide table layout',
          answer: TABLE_MARKDOWN,
          published_at: '2026-07-24T00:00:00Z',
          view_count: 1
        }
      })
    })
  })

  await page.goto(`/lens/qa/${SHARE_TOKEN}`)
  await expect(
    page.getByRole('heading', { name: 'Wide table layout' })
  ).toBeVisible()

  const tableScroll = page.locator('.qa-screen-view .markdown-table-scroll')
  await expect(tableScroll).toHaveCount(1)

  const layout = await page.evaluate(() => {
    const scroll = document.querySelector('.markdown-table-scroll')
    return {
      pageClientWidth: document.documentElement.clientWidth,
      pageScrollWidth: document.documentElement.scrollWidth,
      tableClientWidth: scroll.clientWidth,
      tableScrollWidth: scroll.scrollWidth,
      overflowX: getComputedStyle(scroll).overflowX
    }
  })

  expect(layout.pageScrollWidth).toBe(layout.pageClientWidth)
  expect(layout.tableScrollWidth).toBeGreaterThan(layout.tableClientWidth)
  expect(layout.overflowX).toBe('auto')
})

test('shared Q&A tables retain their desktop styling', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.route(`**/api/lens/public/qa/${SHARE_TOKEN}/`, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          title: 'Desktop table layout',
          question: 'Desktop table layout',
          answer: TABLE_MARKDOWN,
          published_at: '2026-07-24T00:00:00Z',
          view_count: 1
        }
      })
    })
  })

  await page.goto(`/lens/qa/${SHARE_TOKEN}`)
  await expect(
    page.getByRole('heading', { name: 'Desktop table layout' })
  ).toBeVisible()

  const layout = await page.evaluate(() => {
    const scroll = document.querySelector('.markdown-table-scroll')
    const table = scroll.querySelector('table')
    const scrollStyle = getComputedStyle(scroll)
    const tableStyle = getComputedStyle(table)

    return {
      pageClientWidth: document.documentElement.clientWidth,
      pageScrollWidth: document.documentElement.scrollWidth,
      wrapperBorderWidth: scrollStyle.borderWidth,
      wrapperPadding: scrollStyle.padding,
      tableBorderCollapse: tableStyle.borderCollapse,
      tableWidth: table.offsetWidth,
      wrapperWidth: scroll.clientWidth
    }
  })

  expect(layout.pageScrollWidth).toBe(layout.pageClientWidth)
  expect(layout.wrapperBorderWidth).toBe('0px')
  expect(layout.wrapperPadding).toBe('0px')
  expect(layout.tableBorderCollapse).toBe('collapse')
  expect(layout.tableWidth).toBeGreaterThanOrEqual(layout.wrapperWidth)
})

function sharedFile(uuid, filename, contentType, byteSize = 32) {
  return {
    uuid,
    url: `/api/lens/public/qa/${SHARE_TOKEN}/files/${uuid}/`,
    filename,
    content_type: contentType,
    byte_size: byteSize,
    order: 0
  }
}

async function routeCompleteShare(page, outputFiles) {
  await page.route(`**/api/lens/public/qa/${SHARE_TOKEN}/`, async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        data: {
          title: 'Complete shared turn',
          question: 'What does the attached diagram show?',
          input_attachments: [
            sharedFile(INPUT_UUID, 'diagram.png', 'image/png')
          ],
          answer: 'It shows the deployment flow.',
          output_files: outputFiles,
          assistant_name: 'Deployment Agent',
          assistant_slug: 'deployment-agent',
          published_at: '2026-07-25T00:00:00Z',
          view_count: 1
        }
      })
    })
  })
}

test('shared page keeps question attachments and output files in context', async ({
  page
}) => {
  await routeCompleteShare(page, [
    sharedFile(HTML_UUID, 'report.html', 'text/html')
  ])

  await page.goto(`/lens/qa/${SHARE_TOKEN}`)

  const screen = page.locator('.qa-screen-view')

  await expect(
    page.getByRole('heading', { name: 'Complete shared turn' })
  ).toBeVisible()
  await expect(
    screen.getByText('What does the attached diagram show?')
  ).toBeVisible()
  await expect(screen.getByText('diagram.png')).toBeVisible()
  await expect(screen.getByText('It shows the deployment flow.')).toBeVisible()
  await expect(screen.getByText('report.html')).toBeVisible()
})

test('shared Q&A identifies the Agent and downloads the server PDF', async ({
  page
}) => {
  await routeCompleteShare(page, [
    sharedFile(HTML_UUID, 'report.html', 'text/html')
  ])
  await page.goto(`/lens/qa/${SHARE_TOKEN}`)

  const screen = page.locator('.qa-screen-view')
  await expect(screen.getByText('AI Agent Q&A', { exact: true })).toBeVisible()
  await expect(
    screen.getByText('Answer from AI Agent “Deployment Agent”', { exact: true })
  ).toBeVisible()

  await page.route(
    `**/api/lens/public/qa/${SHARE_TOKEN}/export-pdf/`,
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/pdf',
        headers: {
          'Content-Disposition':
            'attachment; filename="shared-agent-answer.pdf"'
        },
        body: Buffer.from('%PDF-1.7\ntest')
      })
    }
  )
  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export PDF' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('shared-agent-answer.pdf')

  await page.emulateMedia({ media: 'print' })
  await expect(screen).toBeHidden()
  const printable = page.locator('.qa-print-view')
  await expect(printable).toBeVisible()
  await expect(printable).toContainText('What does the attached diagram show?')
  await expect(printable).toContainText('It shows the deployment flow.')
  await expect(printable).toContainText('diagram.png')
  await expect(printable).toContainText('report.html')
})

test('shared PDF export falls back to browser print on service failure', async ({
  page
}) => {
  await routeCompleteShare(page, [])
  await page.route(
    `**/api/lens/public/qa/${SHARE_TOKEN}/export-pdf/`,
    async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'PDF_GENERATION_UNAVAILABLE' })
      })
    }
  )
  await page.goto(`/lens/qa/${SHARE_TOKEN}`)
  await page.evaluate(() => {
    window.print = () => {
      document.documentElement.dataset.printRequested = 'true'
    }
  })
  await page.getByRole('button', { name: 'Export PDF' }).click()
  await expect(page.locator('html')).toHaveAttribute(
    'data-print-requested',
    'true'
  )
  await expect(
    page.getByText(
      'Server PDF generation failed. Browser print opened instead.'
    )
  ).toBeVisible()
})

test('shared HTML preview uses a blob URL and an empty sandbox', async ({
  page
}) => {
  await routeCompleteShare(page, [
    sharedFile(HTML_UUID, 'report.html', 'text/html')
  ])
  await page.route(
    `**/api/lens/public/qa/${SHARE_TOKEN}/files/${HTML_UUID}/`,
    async (route) => {
      await route.fulfill({
        contentType: 'text/html',
        body: '<script>parent.document.body.dataset.compromised="yes"</script>'
      })
    }
  )

  await page.goto(`/lens/qa/${SHARE_TOKEN}`)
  await page.getByRole('button', { name: 'Preview report.html' }).click()

  const frame = page.locator('iframe[title="report.html"]')
  await expect(frame).toHaveAttribute('sandbox', '')
  await expect(frame).toHaveAttribute('src', /^blob:/)
  await expect(page.locator('body')).not.toHaveAttribute(
    'data-compromised',
    'yes'
  )
})

test('shared file preview failure falls back to download-only behavior', async ({
  page
}) => {
  await routeCompleteShare(page, [
    sharedFile(BROKEN_UUID, 'broken.txt', 'text/plain'),
    sharedFile(ARCHIVE_UUID, 'archive.zip', 'application/zip')
  ])
  await page.route(
    `**/api/lens/public/qa/${SHARE_TOKEN}/files/${BROKEN_UUID}/`,
    async (route) => route.fulfill({ status: 404 })
  )
  await page.route(
    `**/api/lens/public/qa/${SHARE_TOKEN}/files/${ARCHIVE_UUID}/`,
    async (route) => {
      await route.fulfill({
        contentType: 'application/zip',
        body: 'archive bytes'
      })
    }
  )

  await page.goto(`/lens/qa/${SHARE_TOKEN}`)
  await page.getByRole('button', { name: 'Preview broken.txt' }).click()
  await expect(
    page.getByText('Preview failed, please download instead.')
  ).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()

  const downloadPromise = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Download archive.zip' }).click()
  const download = await downloadPromise
  expect(download.suggestedFilename()).toBe('archive.zip')
})
