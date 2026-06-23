/**
 * Role-based assistant list visibility.
 * Public is visible to every signed-in user; private only to granted
 * users/groups and admins.
 */
import { expect, test } from '@playwright/test'

import { authHeader, fixtures, listSlugs } from './helpers.js'

const f = fixtures()
const PUBLIC = f.assistants.public.slug
const PRIVATE = f.assistants.private.slug

async function slugsFor(request, role) {
  const res = await request.get('/api/lens/assistants/', {
    headers: authHeader(role)
  })
  expect(res.ok()).toBeTruthy()
  return listSlugs(await res.json())
}

test.describe('Assistant list visibility', () => {
  test('plain user sees public but not private', async ({ request }) => {
    const slugs = await slugsFor(request, 'user')
    expect(slugs).toContain(PUBLIC)
    expect(slugs).not.toContain(PRIVATE)
  })

  test('directly authorized user sees private', async ({ request }) => {
    const slugs = await slugsFor(request, 'authuser')
    expect(slugs).toContain(PUBLIC)
    expect(slugs).toContain(PRIVATE)
  })

  test('group-authorized user sees private', async ({ request }) => {
    const slugs = await slugsFor(request, 'groupuser')
    expect(slugs).toContain(PRIVATE)
  })

  test('admin sees both', async ({ request }) => {
    const slugs = await slugsFor(request, 'admin')
    expect(slugs).toContain(PUBLIC)
    expect(slugs).toContain(PRIVATE)
  })

  test('anonymous cannot list assistants', async ({ request }) => {
    const res = await request.get('/api/lens/assistants/')
    expect(res.status()).toBe(401)
  })
})
