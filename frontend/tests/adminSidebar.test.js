import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getAdminSidebarMenu,
  toggleAdminSidebarMenu
} from '../src/admin/layout/adminSidebarState.js'

test('admin routes select their owning sidebar menu', () => {
  const routes = [
    ['/management/lens/runs/42', 'lens'],
    ['/management/lens/datasources', 'data'],
    ['/management/lens/resources/skills', 'data'],
    ['/management/users/42', 'users'],
    ['/management/groups', 'users'],
    ['/management/llm/config', 'llm'],
    ['/management/task-management/list', 'tasks'],
    ['/management/notifier/settings', 'notifications']
  ]

  for (const [path, expectedMenu] of routes) {
    assert.equal(getAdminSidebarMenu(path), expectedMenu)
  }
})

test('standalone routes do not belong to an accordion menu', () => {
  assert.equal(getAdminSidebarMenu('/management'), null)
  assert.equal(getAdminSidebarMenu('/'), null)
})

test('selecting a menu opens it and selecting it again closes it', () => {
  assert.equal(toggleAdminSidebarMenu(null, 'lens'), 'lens')
  assert.equal(toggleAdminSidebarMenu('lens', 'data'), 'data')
  assert.equal(toggleAdminSidebarMenu('data', 'data'), null)
})
