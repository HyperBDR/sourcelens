import assert from 'node:assert/strict'
import test from 'node:test'

import {
  MAX_SKILL_PACKAGE_BYTES,
  skillPackageValidationError
} from '../src/pages/lens/skillPackageValidation.js'

test('accepts a 35 MB Skill zip package', () => {
  const file = {
    name: 'binary-skill.zip',
    size: 35 * 1024 * 1024
  }

  assert.equal(skillPackageValidationError(file), '')
})

test('rejects a Skill zip package over 50 MB', () => {
  const file = {
    name: 'oversized-skill.zip',
    size: MAX_SKILL_PACKAGE_BYTES + 1
  }

  assert.equal(skillPackageValidationError(file), 'packageFileTooLarge')
})

test('rejects a non-zip Skill package', () => {
  const file = {
    name: 'binary-skill.tar.gz',
    size: 35 * 1024 * 1024
  }

  assert.equal(skillPackageValidationError(file), 'packageFileInvalidType')
})
