/**
 * Anonymous access: public assistants and their Q&A are reachable without
 * login; private ones (and their Q&A) return 404. Protected SPA routes
 * redirect to /login.
 */
import { expect, test } from '@playwright/test'

import { fixtures } from './helpers.js'

const f = fixtures()
const PUBLIC = f.assistants.public.slug
const PRIVATE = f.assistants.private.slug
const PUBLIC_SHARE = f.shares.public_token
const PRIVATE_SHARE = f.shares.private_token

test.describe('Anonymous public surface', () => {
  test('public assistant metadata is reachable', async ({ request }) => {
    const res = await request.get(`/api/lens/public/assistants/${PUBLIC}/`)
    expect(res.status()).toBe(200)
  })

  test('private assistant metadata is hidden (404)', async ({ request }) => {
    const res = await request.get(`/api/lens/public/assistants/${PRIVATE}/`)
    expect(res.status()).toBe(404)
  })

  test('public assistant Q&A list is reachable', async ({ request }) => {
    const res = await request.get(`/api/lens/public/assistants/${PUBLIC}/qa/`)
    expect(res.status()).toBe(200)
  })

  test('private assistant Q&A list is hidden (404)', async ({ request }) => {
    const res = await request.get(`/api/lens/public/assistants/${PRIVATE}/qa/`)
    expect(res.status()).toBe(404)
  })

  test('public shared Q&A token is reachable', async ({ request }) => {
    const res = await request.get(`/api/lens/public/qa/${PUBLIC_SHARE}/`)
    expect(res.status()).toBe(200)
  })

  test('private assistant shared Q&A token is hidden (404)', async ({
    request
  }) => {
    const res = await request.get(`/api/lens/public/qa/${PRIVATE_SHARE}/`)
    expect(res.status()).toBe(404)
  })

  test('protected route redirects anonymous to /login', async ({ page }) => {
    await page.context().clearCookies()
    await page.goto('/management/lens/assistants', {
      waitUntil: 'domcontentloaded'
    })
    await page.waitForURL(/\/login/, { timeout: 10000 })
    expect(page.url()).toContain('/login')
  })
})
