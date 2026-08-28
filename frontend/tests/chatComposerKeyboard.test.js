import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

test('submits with Enter and preserves multiline input with Ctrl+Enter', async () => {
  const source = await readFile(
    new URL('../src/pages/lens/Chat.vue', import.meta.url),
    'utf8'
  )

  assert.match(source, /@keydown\.enter\.exact\.prevent="handlePrimaryAction"/)
  assert.match(source, /@keydown\.ctrl\.enter\.exact\.prevent="insertNewline"/)
})
