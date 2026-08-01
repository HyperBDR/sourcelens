import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const readSource = (path) =>
  readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('complete assistant and LensNode reads collect every API page', async () => {
  const source = await readSource('api/lens.js')
  const assistants = source.slice(
    source.indexOf('export async function listAssistants'),
    source.indexOf('export async function getPublicAssistant')
  )
  const lensnodes = source.slice(
    source.indexOf('export async function listLensNodes'),
    source.indexOf('export async function getAdminRuns')
  )

  assert.match(assistants, /collectPaginatedResults/)
  assert.match(lensnodes, /collectPaginatedResults/)
})

test('shared Q&A review uses backend pagination metadata', async () => {
  const source = await readSource('admin/pages/lens/ShareReview.vue')

  assert.match(source, /const totalCount = ref\(0\)/)
  assert.match(source, /page: currentPage\.value/)
  assert.match(source, /page_size: pageSize\.value/)
  assert.match(source, /:total="totalCount"/)
  assert.match(source, /goPrevPage[\s\S]*load\(\)/)
  assert.match(source, /goNextPage[\s\S]*load\(\)/)
})

test('management selectors collect all user and group pages', async () => {
  const [api, groups, users, tasks] = await Promise.all([
    readSource('admin/api/management.js'),
    readSource('admin/pages/Management/Groups.vue'),
    readSource('admin/pages/Management/Users.vue'),
    readSource('admin/pages/TaskManagement/List.vue')
  ])

  assert.match(api, /getAllUsers[\s\S]*collectPaginatedResults/)
  assert.match(api, /getAllGroups[\s\S]*collectPaginatedResults/)
  assert.match(groups, /managementApi\.getAllUsers/)
  assert.match(groups, /const userOptionsLoaded = ref\(false\)/)
  assert.match(
    groups,
    /if \(userOptionsLoaded\.value\)[\s\S]*payload\.user_ids/
  )
  assert.match(users, /managementApi\.getAllGroups/)
  assert.match(tasks, /managementApi\.getAllUsers/)
})
