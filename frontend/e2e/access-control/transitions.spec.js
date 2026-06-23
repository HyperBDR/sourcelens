/**
 * Dynamic permission changes take effect immediately: flipping visibility or
 * revoking a grant removes access. Each test restores the seeded baseline.
 */
import { expect, test } from '@playwright/test'

import { authHeader, fixtures, listSlugs } from './helpers.js'

const f = fixtures()
const PUBLIC = f.assistants.public
const PRIVATE = f.assistants.private
const GROUP_ID = f.group_id
const AUTHUSER_ID = f.user_ids.authuser

async function patchAssistant(request, uuid, data) {
  const res = await request.patch(`/api/lens/assistants/${uuid}/`, {
    headers: authHeader('admin'),
    data
  })
  expect(res.ok()).toBeTruthy()
}

async function userSlugs(request, role) {
  const res = await request.get('/api/lens/assistants/', {
    headers: authHeader(role)
  })
  return listSlugs(await res.json())
}

async function sessionStatus(request, role, uuid) {
  const res = await request.post('/api/lens/sessions/', {
    headers: authHeader(role),
    data: { assistant_uuid: uuid }
  })
  return res.status()
}

test.describe('Dynamic permission changes', () => {
  test('flipping public to private removes a plain user access', async ({
    request
  }) => {
    try {
      await patchAssistant(request, PUBLIC.uuid, {
        visibility: 'private',
        access_grants: []
      })
      expect(await userSlugs(request, 'user')).not.toContain(PUBLIC.slug)
      expect(await sessionStatus(request, 'user', PUBLIC.uuid)).toBe(403)
    } finally {
      await patchAssistant(request, PUBLIC.uuid, {
        visibility: 'public',
        access_grants: []
      })
    }
    expect(await sessionStatus(request, 'user', PUBLIC.uuid)).toBe(201)
  })

  test('revoking a direct grant removes that user access', async ({
    request
  }) => {
    try {
      // keep only the group grant -> authuser (not in group) loses access
      await patchAssistant(request, PRIVATE.uuid, {
        access_grants: [{ type: 'group', id: GROUP_ID }]
      })
      expect(await userSlugs(request, 'authuser')).not.toContain(PRIVATE.slug)
      expect(await sessionStatus(request, 'authuser', PRIVATE.uuid)).toBe(403)
      // group user still has access via the group
      expect(await sessionStatus(request, 'groupuser', PRIVATE.uuid)).toBe(201)
    } finally {
      await patchAssistant(request, PRIVATE.uuid, {
        access_grants: [
          { type: 'group', id: GROUP_ID },
          { type: 'user', id: AUTHUSER_ID }
        ]
      })
    }
    expect(await sessionStatus(request, 'authuser', PRIVATE.uuid)).toBe(201)
  })
})
