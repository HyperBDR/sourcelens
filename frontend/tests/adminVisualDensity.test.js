import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (path) =>
  readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('admin shell uses a compact modern navigation scale', async () => {
  const [header, sidebar] = await Promise.all([
    source('admin/layout/AdminHeader.vue'),
    source('admin/layout/AdminSidebar.vue')
  ])

  assert.match(header, /h-14/)
  assert.match(sidebar, /h-14/)
  assert.match(sidebar, /w-60/)
  assert.match(sidebar, /text-\[13px\]/)
})

test('statistics pages share the compact surface and typography contract', async () => {
  const [styles, ...pages] = await Promise.all([
    source('assets/css/main.css'),
    source('admin/pages/LLM/Stats.vue'),
    source('admin/pages/TaskManagement/Stats.vue'),
    source('admin/pages/Notifications/Stats.vue')
  ])

  assert.match(styles, /\.admin-stats-page/)
  assert.match(styles, /\.admin-filter-toolbar/)
  assert.match(styles, /\.admin-metric-value/)
  for (const contents of pages) {
    assert.match(contents, /admin-stats-page/)
    assert.match(contents, /admin-filter-toolbar/)
  }
})

test('operations summaries use compact numeric emphasis', async () => {
  const [runs, nodes] = await Promise.all([
    source('admin/pages/lens/RunObservation.vue'),
    source('pages/lens/LensNodes.vue')
  ])

  assert.match(runs, /admin-metric-value/)
  assert.match(nodes, /admin-metric-value/)
  assert.doesNotMatch(runs, /text-2xl/)
  assert.doesNotMatch(nodes, /text-2xl/)
})
