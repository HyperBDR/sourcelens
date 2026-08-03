import assert from 'node:assert/strict'
import test from 'node:test'

import { skillErrorMessage } from '../src/pages/lens/skillErrorMessage.js'

const t = (key) => `translated:${key}`
const fallback = 'translated:lensAdmin.messages.saveFailed'

function apiError(detail) {
  return {
    response: {
      data: { detail }
    }
  }
}

test('localizes the oversized Skill package file error', () => {
  const message = skillErrorMessage(
    apiError('Skill package contains an oversized file.'),
    t,
    fallback
  )

  assert.equal(
    message,
    'translated:lensAdmin.skills.errors.packageFileTooLarge'
  )
})

test('localizes common Skill package, SKILL.md, and GitHub errors', () => {
  const cases = [
    ['Skill package must be a valid zip archive.', 'packageInvalidZip'],
    ['Skill package contains unsafe paths.', 'packageUnsafePaths'],
    ['SKILL.md requires name and description.', 'skillMdMetadataRequired'],
    ['GitHub URL is required.', 'githubUrlRequired'],
    ['GitHub download failed: HTTP 404', 'githubDownloadFailed']
  ]

  for (const [detail, key] of cases) {
    assert.equal(
      skillErrorMessage(apiError(detail), t, fallback),
      `translated:lensAdmin.skills.errors.${key}`
    )
  }
})

test('localizes Skill configuration validation error families', () => {
  const cases = [
    [
      "Artifact 'income' SHA-256 does not match its packaged file.",
      'artifactInvalid'
    ],
    [
      "Transform 'summarize' entrypoint must reference a regular file.",
      'transformInvalid'
    ],
    ['Environment variables must be provided as a list.', 'environmentInvalid'],
    ['The Skill API policy must be an object.', 'apiPolicyInvalid']
  ]

  for (const [detail, key] of cases) {
    assert.equal(
      skillErrorMessage(apiError(detail), t, fallback),
      `translated:lensAdmin.skills.errors.${key}`
    )
  }
})

test('uses the localized operation fallback for unknown API details', () => {
  assert.equal(
    skillErrorMessage(apiError('Unexpected upstream detail.'), t, fallback),
    fallback
  )
})

test('preserves localized client-side validation errors', () => {
  const error = new Error('请先选择 Skill zip 压缩包。')

  assert.equal(skillErrorMessage(error, t, fallback), error.message)
})
