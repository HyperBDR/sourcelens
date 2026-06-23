/**
 * Role-based chat access: creating a session against a private assistant
 * requires authorization; public is open to any signed-in user.
 */
import { expect, test } from '@playwright/test'

import { authHeader, fixtures } from './helpers.js'

const f = fixtures()
const PUBLIC_UUID = f.assistants.public.uuid
const PRIVATE_UUID = f.assistants.private.uuid

async function createSession(request, role, uuid) {
  return request.post('/api/lens/sessions/', {
    headers: authHeader(role),
    data: { assistant_uuid: uuid }
  })
}

test.describe('Chat (session) access', () => {
  test('plain user can start a public session', async ({ request }) => {
    const res = await createSession(request, 'user', PUBLIC_UUID)
    expect(res.status()).toBe(201)
  })

  test('plain user is blocked from a private session', async ({ request }) => {
    const res = await createSession(request, 'user', PRIVATE_UUID)
    expect(res.status()).toBe(403)
  })

  test('authorized user can start a private session', async ({ request }) => {
    const res = await createSession(request, 'authuser', PRIVATE_UUID)
    expect(res.status()).toBe(201)
  })

  test('group-authorized user can start a private session', async ({
    request
  }) => {
    const res = await createSession(request, 'groupuser', PRIVATE_UUID)
    expect(res.status()).toBe(201)
  })

  test('admin can start a private session', async ({ request }) => {
    const res = await createSession(request, 'admin', PRIVATE_UUID)
    expect(res.status()).toBe(201)
  })
})
