import { expect, test } from '@playwright/test'

const SHARE_TOKEN = 'e2e-wide-table'
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

  const tableScroll = page.locator('.markdown-table-scroll')
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
