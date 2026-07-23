/**
 * Anonymous access: public assistant metadata remains reachable, shared Q&A
 * requires login, and protected SPA routes redirect to /login.
 */
import { expect, test } from '@playwright/test'

import { asRole, fixtures } from './helpers.js'

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

  test('public assistant Q&A list requires login', async ({ request }) => {
    const res = await request.get(`/api/lens/public/assistants/${PUBLIC}/qa/`)
    expect(res.status()).toBe(403)
    expect((await res.json()).code).toBe('AUTHENTICATION_REQUIRED')
  })

  test('private assistant Q&A list requires login', async ({ request }) => {
    const res = await request.get(`/api/lens/public/assistants/${PRIVATE}/qa/`)
    expect(res.status()).toBe(403)
    expect((await res.json()).code).toBe('AUTHENTICATION_REQUIRED')
  })

  test('public shared Q&A token requires login', async ({ request }) => {
    const res = await request.get(`/api/lens/public/qa/${PUBLIC_SHARE}/`)
    expect(res.status()).toBe(403)
    expect((await res.json()).code).toBe('AUTHENTICATION_REQUIRED')
  })

  test('private assistant shared Q&A token requires login', async ({
    request
  }) => {
    const res = await request.get(`/api/lens/public/qa/${PRIVATE_SHARE}/`)
    expect(res.status()).toBe(403)
    expect((await res.json()).code).toBe('AUTHENTICATION_REQUIRED')
  })

  test('valid shared Q&A shows a prominent login prompt', async ({ page }) => {
    await page.goto(`/lens/qa/${PUBLIC_SHARE}`)

    await expect(
      page.getByRole('heading', { name: 'Sign in to view this Q&A' })
    ).toBeVisible()
    await page.getByRole('button', { name: 'Sign in to continue' }).click()
    await expect(page).toHaveURL(/\/login\?next=/)
    expect(new URL(page.url()).searchParams.get('next')).toBe(
      `/lens/qa/${PUBLIC_SHARE}`
    )
  })

  test('missing shared Q&A remains not found', async ({ page }) => {
    await page.goto('/lens/qa/e2e-missing-share')

    await expect(
      page.getByText("This Q&A doesn't exist or has been unshared.")
    ).toBeVisible()
    await expect(
      page.getByRole('heading', { name: 'Sign in to view this Q&A' })
    ).toHaveCount(0)
  })

  test('authenticated viewer without assistant access is denied', async ({
    page
  }) => {
    await asRole(page, 'user')
    await page.goto(`/lens/qa/${PRIVATE_SHARE}`)

    await expect(
      page.getByRole('heading', { name: "You don't have access" })
    ).toBeVisible()
  })

  test('authenticated hydration loads a shared Q&A once', async ({ page }) => {
    await asRole(page, 'user')
    let requests = 0
    const profileResponse = page.waitForResponse((response) => {
      return new URL(response.url()).pathname === '/api/v1/auth/user'
    })
    page.on('request', (request) => {
      const path = new URL(request.url()).pathname
      if (path === `/api/lens/public/qa/${PUBLIC_SHARE}/`) {
        requests += 1
      }
    })

    await page.goto(`/lens/qa/${PUBLIC_SHARE}`)
    await profileResponse
    await expect(
      page.getByRole('heading', { name: 'E2E Public share' })
    ).toBeVisible()
    await page.evaluate(
      () =>
        new Promise((resolve) => {
          requestAnimationFrame(() => requestAnimationFrame(resolve))
        })
    )
    expect(requests).toBe(1)
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
