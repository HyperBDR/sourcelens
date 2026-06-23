/**
 * Only admin-console users may create/edit assistants and manage access.
 * Plain users are blocked at the API (403) and the admin console UI.
 */
import { expect, test } from '@playwright/test'

import { asRole, authHeader, fixtures } from './helpers.js'

const f = fixtures()
const PUBLIC_UUID = f.assistants.public.uuid

test.describe('Assistant write gate (API)', () => {
  test('plain user cannot edit an assistant', async ({ request }) => {
    const res = await request.patch(`/api/lens/assistants/${PUBLIC_UUID}/`, {
      headers: authHeader('user'),
      data: { max_concurrency: 6 }
    })
    expect(res.status()).toBe(403)
  })

  test('plain user cannot create an assistant', async ({ request }) => {
    const res = await request.post('/api/lens/assistants/', {
      headers: authHeader('user'),
      data: { name: 'Nope', slug: 'e2e-nope' }
    })
    expect(res.status()).toBe(403)
  })

  test('admin can edit an assistant', async ({ request }) => {
    const res = await request.patch(`/api/lens/assistants/${PUBLIC_UUID}/`, {
      headers: authHeader('admin'),
      data: { max_concurrency: 6 }
    })
    expect(res.status()).toBe(200)
  })
})

test.describe('Admin console access (UI)', () => {
  test('admin sees the assistants console with a Visibility column', async ({
    page
  }) => {
    await asRole(page, 'admin')
    await page.goto('/management/lens/assistants', {
      waitUntil: 'domcontentloaded'
    })
    await expect(
      page.getByRole('columnheader', { name: /Visibility|可见性/ })
    ).toBeVisible({ timeout: 15000 })
  })

  test('plain user is redirected away from the assistants console', async ({
    page
  }) => {
    await asRole(page, 'user')
    await page.goto('/management/lens/assistants', {
      waitUntil: 'domcontentloaded'
    })
    await page.waitForTimeout(2000)
    expect(page.url()).not.toContain('/management/lens/assistants')
  })
})
