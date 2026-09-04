import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (path) =>
  readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('Plugin releases have an administrator lifecycle surface', async () => {
  const [page, api, routes, sidebar, chinese] = await Promise.all([
    source('pages/lens/PluginReleases.vue'),
    source('api/lens.js'),
    source('admin/routes.js'),
    source('admin/layout/AdminSidebar.vue'),
    source('admin/locales/zh-CN.json')
  ])

  assert.match(api, /listPluginReleases/)
  assert.match(api, /reconcilePluginReleases/)
  assert.match(api, /publishPluginRelease/)
  assert.match(api, /setPluginReleaseRole/)
  assert.match(api, /retirePluginRelease/)
  assert.match(routes, /name: 'LensPluginReleases'/)
  assert.match(sidebar, /resources\/plugins/)
  assert.match(page, /release_status/)
  assert.match(page, /deployment_role/)
  assert.match(page, /integrity_ok/)
  assert.match(page, /publishPluginRelease/)
  assert.match(page, /setPluginReleaseRole/)
  assert.match(page, /retirePluginRelease/)
  assert.doesNotMatch(page, /type="file"/)
  assert.match(chinese, /调试中/)
  assert.match(chinese, /候选版本/)
  assert.match(chinese, /生产版本/)
})
