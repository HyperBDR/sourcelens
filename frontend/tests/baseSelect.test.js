import assert from 'node:assert/strict'
import { readdir, readFile } from 'node:fs/promises'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import { applyModelModifiers } from '../src/components/ui/baseSelect.js'

const source = (relativePath) =>
  readFile(new URL(`../src/${relativePath}`, import.meta.url), 'utf8')

async function listVueFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true })
  const files = await Promise.all(
    entries.map(async (entry) => {
      const entryPath = path.join(directory, entry.name)
      return entry.isDirectory() ? listVueFiles(entryPath) : [entryPath]
    })
  )
  return files.flat().filter((file) => file.endsWith('.vue'))
}

test('BaseSelect exposes the native select contract and visual variants', async () => {
  const component = await source('components/ui/BaseSelect.vue')

  assert.match(component, /inheritAttrs:\s*false/)
  assert.match(component, /v-bind="selectAttrs"/)
  assert.match(component, /v-model="selectedValue"/)
  assert.match(component, /@change="handleChange"/)
  assert.match(component, /\['sm', 'md', 'lg'\]/)
  assert.match(component, /\['default', 'unstyled'\]/)
  assert.match(component, /appearance-none/)
  assert.match(component, /aria-invalid/)
  assert.match(component, /update:modelValue/)
  assert.match(component, /'change'/)
  assert.match(component, /'focus'/)
  assert.match(component, /'blur'/)
})

test('BaseSelect preserves values received from bound native options', () => {
  const objectValue = { id: 'model-a' }

  assert.equal(applyModelModifiers(objectValue), objectValue)
})

test('BaseSelect applies the number model modifier to native string values', () => {
  assert.equal(applyModelModifiers('20', { number: true }), 20)
  assert.equal(
    applyModelModifiers('not-a-number', { number: true }),
    'not-a-number'
  )
  assert.equal(applyModelModifiers('20'), '20')
})

test('all production selects use BaseSelect while prototypes stay native', async () => {
  const srcDirectory = fileURLToPath(new URL('../src/', import.meta.url))
  const files = await listVueFiles(srcDirectory)
  const productionFiles = files.filter(
    (file) =>
      !file.includes(`${path.sep}design${path.sep}ai-query-v1${path.sep}`) &&
      !file.endsWith(
        `${path.sep}components${path.sep}ui${path.sep}BaseSelect.vue`
      )
  )
  const nativeSelects = []

  for (const file of productionFiles) {
    const contents = await readFile(file, 'utf8')
    if (/<select\b/.test(contents)) {
      nativeSelects.push(path.relative(srcDirectory, file))
    }
  }

  assert.deepEqual(nativeSelects, [])

  const prototype = await source('design/ai-query-v1/App.vue')
  assert.equal(prototype.match(/<select\b/g)?.length, 3)
  assert.doesNotMatch(prototype, /BaseSelect/)
})
