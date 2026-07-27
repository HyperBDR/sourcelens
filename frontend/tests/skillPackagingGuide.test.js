import assert from 'node:assert/strict'
import test from 'node:test'

import {
  buildSkillPackagingPrompt,
  copySkillPackagingPrompt
} from '../src/pages/lens/skillPackagingGuide.js'

test('appends the declared Transform contract to the packaging prompt', () => {
  assert.equal(
    buildSkillPackagingPrompt('Base requirements.', 'Transform contract.'),
    'Base requirements.\n\nTransform contract.'
  )
})

test('copies the complete Skill packaging prompt without expanding it', async () => {
  const copiedTexts = []
  const prompt = 'Package this Skill as a SourceLens-compatible zip.'

  const copied = await copySkillPackagingPrompt(prompt, async (text) => {
    copiedTexts.push(text)
    return true
  })

  assert.equal(copied, true)
  assert.deepEqual(copiedTexts, [prompt])
})

test('reports a failed Skill packaging prompt copy', async () => {
  const copied = await copySkillPackagingPrompt(
    'Package this Skill.',
    async () => false
  )

  assert.equal(copied, false)
})
