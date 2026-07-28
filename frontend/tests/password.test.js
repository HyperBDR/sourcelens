import assert from 'node:assert/strict'
import test from 'node:test'

import {
  getPasswordManagementText,
  passwordManagementMessages
} from '../src/locales/passwordManagement.js'
import {
  getApiErrorData,
  getFirstApiError,
  getPasswordPolicyError
} from '../src/utils/password.js'

test('validates password policy boundaries and character requirements', () => {
  assert.equal(getPasswordPolicyError('A1short'), 'tooShort')
  assert.equal(getPasswordPolicyError(`A1${'x'.repeat(31)}`), 'tooLong')
  assert.equal(getPasswordPolicyError('onlyletters'), 'requirements')
  assert.equal(getPasswordPolicyError('12345678'), 'requirements')
  assert.equal(getPasswordPolicyError('R7vM2Qp9'), '')
})

test('provides complete English and Chinese password messages', () => {
  assert.ok(passwordManagementMessages.en.passwordManagement.forgot.success)
  assert.ok(
    passwordManagementMessages['zh-CN'].passwordManagement.security.success
  )
  assert.equal(getPasswordManagementText('en-US').security.title, 'Security')
  assert.equal(getPasswordManagementText('zh-CN').security.title, '安全')
  assert.equal(
    getPasswordManagementText('en-US').security.forgotPassword,
    'Forgot your current password?'
  )
  assert.equal(
    getPasswordManagementText('zh-CN').security.forgotPassword,
    '忘记当前密码？'
  )
})

test('unwraps unified API errors and reads the first field error', () => {
  const error = {
    response: {
      data: {
        data: {
          errors: {
            newPassword1: ['Password is too common']
          }
        }
      }
    }
  }

  assert.deepEqual(getApiErrorData(error), error.response.data.data)
  assert.equal(getFirstApiError(error), 'Password is too common')
})

test('reads Django non-field password validation errors', () => {
  const error = {
    response: {
      data: {
        data: {
          non_field_errors: ['Password is too similar to the username']
        }
      }
    }
  }

  assert.equal(
    getFirstApiError(error),
    'Password is too similar to the username'
  )
})
