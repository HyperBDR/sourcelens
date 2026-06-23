/**
 * Admin management console: group CRUD + membership, user disable-only
 * (never delete), and the cascade that revokes a group's assistant grants
 * when the group is deleted.
 */
import { expect, test } from '@playwright/test'

import { authHeader, fixtures } from './helpers.js'

const f = fixtures()
const ADMIN = authHeader('admin')
const USER_ID = f.user_ids.user
const PRIVATE_UUID = f.assistants.private.uuid

function data(body) {
  return body?.data ?? body
}

async function createGroup(request, userIds = []) {
  const res = await request.post('/api/v1/management/groups/', {
    headers: ADMIN,
    data: {
      name: `e2e_mgmt_${Date.now()}_${Math.floor(Math.random() * 1e6)}`,
      user_ids: userIds
    }
  })
  expect(res.ok()).toBeTruthy()
  return data(await res.json())
}

async function listGroups(request) {
  const res = await request.get('/api/v1/management/groups/?page_size=1000', {
    headers: ADMIN
  })
  const d = data(await res.json())
  return Array.isArray(d) ? d : (d.results ?? [])
}

function deleteGroup(request, id) {
  return request.delete(`/api/v1/management/groups/${id}/`, { headers: ADMIN })
}

async function privateGrants(request) {
  const res = await request.get(`/api/lens/assistants/${PRIVATE_UUID}/`, {
    headers: ADMIN
  })
  return data(await res.json()).access_grants
}

test.describe('Management: groups', () => {
  test('create and delete a group', async ({ request }) => {
    const group = await createGroup(request)
    expect((await listGroups(request)).some((g) => g.id === group.id)).toBe(
      true
    )
    const del = await deleteGroup(request, group.id)
    expect(del.status()).toBe(204)
    expect((await listGroups(request)).some((g) => g.id === group.id)).toBe(
      false
    )
  })

  test('add and remove a member', async ({ request }) => {
    const group = await createGroup(request)
    try {
      const added = await request.patch(
        `/api/v1/management/groups/${group.id}/`,
        { headers: ADMIN, data: { user_ids: [USER_ID] } }
      )
      expect(data(await added.json()).user_count).toBe(1)

      const removed = await request.patch(
        `/api/v1/management/groups/${group.id}/`,
        { headers: ADMIN, data: { user_ids: [] } }
      )
      expect(data(await removed.json()).user_count).toBe(0)
    } finally {
      await deleteGroup(request, group.id)
    }
  })
})

test.describe('Management: users are disabled, never deleted', () => {
  test('user delete endpoint is not allowed (405)', async ({ request }) => {
    const res = await request.delete(`/api/v1/management/users/${USER_ID}/`, {
      headers: ADMIN
    })
    expect(res.status()).toBe(405)
  })

  test('disable then re-enable a user', async ({ request }) => {
    try {
      const off = await request.patch(`/api/v1/management/users/${USER_ID}/`, {
        headers: ADMIN,
        data: { is_active: false }
      })
      expect(off.ok()).toBeTruthy()

      const list = await request.get(
        '/api/v1/management/users/?page_size=1000',
        { headers: ADMIN }
      )
      const users = data(await list.json()).results ?? data(await list.json())
      expect(users.find((u) => u.id === USER_ID).is_active).toBe(false)
    } finally {
      await request.patch(`/api/v1/management/users/${USER_ID}/`, {
        headers: ADMIN,
        data: { is_active: true }
      })
    }
  })
})

test.describe('Management: deleting a group revokes its assistant grants', () => {
  test('group deletion cascades AssistantAccess', async ({ request }) => {
    const baseline = (await privateGrants(request)).map((g) => ({
      type: g.type,
      id: g.id
    }))
    const group = await createGroup(request)
    let deleted = false
    try {
      const patch = await request.patch(
        `/api/lens/assistants/${PRIVATE_UUID}/`,
        {
          headers: ADMIN,
          data: {
            access_grants: [...baseline, { type: 'group', id: group.id }]
          }
        }
      )
      expect(patch.ok()).toBeTruthy()

      const withGrant = (await listGroups(request)).find(
        (g) => g.id === group.id
      )
      expect(withGrant.assistant_grant_count).toBe(1)

      const del = await deleteGroup(request, group.id)
      expect(del.status()).toBe(204)
      deleted = true

      const grants = await privateGrants(request)
      expect(grants.some((g) => g.type === 'group' && g.id === group.id)).toBe(
        false
      )
      expect(grants.length).toBe(baseline.length)
    } finally {
      if (!deleted) {
        await deleteGroup(request, group.id)
        await request.patch(`/api/lens/assistants/${PRIVATE_UUID}/`, {
          headers: ADMIN,
          data: { access_grants: baseline }
        })
      }
    }
  })
})
