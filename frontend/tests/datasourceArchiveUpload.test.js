import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (path) =>
  readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('file datasource APIs send archives as multipart requests', async () => {
  const api = await source('api/lens.js')

  assert.match(api, /export async function uploadDataSourceArchive/)
  assert.match(api, /datasources\/upload\//)
  assert.match(api, /export async function reuploadDataSourceArchive/)
  assert.match(api, /datasources\/\$\{uuid\}\/reupload\//)
  assert.match(api, /form\.append\('metadata', JSON\.stringify\(payload\)\)/)
  assert.match(api, /form\.append\('file', file\)/)
})

test('file datasource wizard requires an archive only on create', async () => {
  const drawer = await source('pages/lens/DataSourceFormDrawer.vue')

  assert.match(drawer, /value: 'file'/)
  assert.match(drawer, /accept="\.zip,\.tar\.gz,\.tgz/)
  assert.match(drawer, /props\.mode === 'edit'.*props\.form\.archive_file/s)
  assert.match(drawer, /step\.key !== 'connection'/)
})

test('datasource save selects create, reupload, or metadata update', async () => {
  const page = await source('pages/lens/DataSources.vue')

  assert.match(page, /uploadDataSourceArchive\(buildPayload\(\),/)
  assert.match(page, /reuploadDataSourceArchive\(uuid, payload,/)
  assert.match(page, /await updateDataSource\(uuid, payload\)/)
  assert.match(page, /\{ conversion: syncPolicy\.conversion \}/)
})
