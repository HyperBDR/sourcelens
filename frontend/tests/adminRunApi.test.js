import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('admin run API exposes operational actions and full export', async () => {
  const contents = await readFile(
    new URL('../src/api/lens.js', import.meta.url),
    'utf8'
  )

  assert.match(contents, /export async function cancelAdminRun/)
  assert.match(contents, /export async function retryAdminRun/)
  assert.match(contents, /export async function resumeAdminRun/)
  assert.match(contents, /export async function getAdminRunTrajectoryExport/)
  assert.match(contents, /collectPaginatedResults/)
})
