import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const componentSource = () =>
  readFile(
    new URL('../src/admin/pages/lens/RunDiagnosisPanel.vue', import.meta.url),
    'utf8'
  )

const apiSource = () =>
  readFile(new URL('../src/api/lens.js', import.meta.url), 'utf8')

test('diagnosis panel exposes generation and evidence-bound follow-up', async () => {
  const contents = await componentSource()

  assert.match(contents, /defineExpose\(\{ generate, load \}\)/)
  assert.match(contents, /data-testid="diagnosis-follow-up"/)
  assert.match(contents, /maxlength="2000"/)
  assert.match(contents, /createAdminRunDiagnosticTurn/)
  assert.match(contents, /emit\('navigate', evidenceRef\)/)
  assert.match(contents, /aria-live="polite"/)
})

test('lens API includes diagnosis list, generate, and follow-up calls', async () => {
  const contents = await apiSource()

  assert.match(contents, /getAdminRunDiagnostics/)
  assert.match(contents, /generateAdminRunDiagnosis/)
  assert.match(contents, /createAdminRunDiagnosticTurn/)
  assert.match(contents, /\/diagnostics\//)
  assert.match(contents, /\/turns\//)
})
