import { expect, test } from '@playwright/test'

import { asRole } from './helpers.js'

test('admin reviews Q&A content and moderates it from the drawer', async ({
  page
}) => {
  const share = {
    uuid: '00000000-0000-0000-0000-000000000026',
    token: 'review-detail-token',
    title: 'Review detail fixture',
    question: 'What content should the reviewer inspect?',
    answer: 'The complete answer must stay visible during moderation.',
    answer_snippet: 'Complete moderation answer.',
    assistant_name: 'Review Assistant',
    assistant_slug: 'review-assistant',
    assistant_visibility: 'public',
    is_listed: false,
    status: 'published',
    published_by: 'review-author',
    view_count: 7,
    published_at: '2026-07-22T08:00:00Z',
    created_at: '2026-07-22T08:00:00Z'
  }
  const patches = []

  await page.route('**/api/lens/admin/shares/**', async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    const isDetail = url.pathname.endsWith(`/${share.uuid}/`)

    if (request.method() === 'PATCH' && isDetail) {
      const payload = request.postDataJSON()
      patches.push(payload)
      Object.assign(share, payload)
      await route.fulfill({ json: share })
      return
    }

    if (request.method() === 'GET' && isDetail) {
      await route.fulfill({ json: share })
      return
    }

    const listed = url.searchParams.get('listed')
    const status = url.searchParams.get('status')
    const matchesListed = listed === null || String(share.is_listed) === listed
    const matchesStatus = !status || share.status === status
    await route.fulfill({
      json: {
        count: matchesListed && matchesStatus ? 1 : 0,
        results: matchesListed && matchesStatus ? [share] : []
      }
    })
  })

  await asRole(page, 'admin')
  await page.goto('/management/lens/shares')

  await page.locator('tbody tr').click()
  const drawer = page.getByRole('dialog', { name: /Q&A detail|问答详情/ })
  await expect(
    drawer.getByText('What content should the reviewer inspect?')
  ).toBeVisible()
  await expect(
    drawer.getByText('The complete answer must stay visible during moderation.')
  ).toBeVisible()

  await drawer.getByRole('button', { name: /Approve|通过上榜/ }).click()
  await expect(
    drawer.getByRole('button', { name: /Remove from list|撤下列表/ })
  ).toBeVisible()

  await drawer.getByRole('button', { name: /Done|完成/ }).click()
  await page.getByRole('button', { name: /^(Listed|已上榜)$/ }).click()
  await page.locator('tbody tr').click()
  await expect(
    drawer.getByText('What content should the reviewer inspect?')
  ).toBeVisible()

  await drawer.getByRole('button', { name: /Take down|下架/ }).click()
  await expect(
    drawer.getByRole('button', { name: /Restore|恢复/ })
  ).toBeVisible()

  await drawer.getByRole('button', { name: /Done|完成/ }).click()
  await page.getByRole('button', { name: /^(Hidden|已下架)$/ }).click()
  await page.locator('tbody tr').click()
  await expect(
    drawer.getByText('The complete answer must stay visible during moderation.')
  ).toBeVisible()

  await drawer.getByRole('button', { name: /Restore|恢复/ }).click()
  await expect(
    drawer.getByRole('button', { name: /Remove from list|撤下列表/ })
  ).toBeVisible()

  expect(patches).toEqual([
    { is_listed: true },
    { status: 'hidden' },
    { status: 'published' }
  ])
})
