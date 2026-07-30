import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  getPasswordManagementText,
  passwordManagementMessages
} from '../src/locales/passwordManagement.js'
import {
  getApiErrorData,
  getFirstApiError,
  getPasswordPolicyError,
  getPasswordSetupErrorKey
} from '../src/utils/password.js'

const source = (path) =>
  readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')

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
  assert.equal(
    getPasswordManagementText('en-US').setup.promptStatus,
    'No sign-in password set'
  )
  assert.equal(
    getPasswordManagementText('zh-CN').setup.promptAction,
    '设置密码'
  )
  assert.ok(getPasswordManagementText('en-US').setup.codeExpired)
  assert.ok(getPasswordManagementText('zh-CN').setup.success)
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

test('maps first-time setup API codes to localized message keys', () => {
  assert.equal(getPasswordSetupErrorKey('RATE_LIMITED'), 'rateLimited')
  assert.equal(getPasswordSetupErrorKey('EXPIRED'), 'codeExpired')
  assert.equal(getPasswordSetupErrorKey('TOO_MANY_ATTEMPTS'), 'tooManyAttempts')
  assert.equal(getPasswordSetupErrorKey('PASSWORD_ALREADY_SET'), 'alreadySet')
  assert.equal(getPasswordSetupErrorKey('UNKNOWN'), 'error')
})

test('exposes a passwordless account prompt that opens Security directly', async () => {
  const [dock, settings] = await Promise.all([
    source('components/lens/UserDock.vue'),
    source('components/settings/UserSettingsModal.vue')
  ])

  assert.match(dock, /can_change_password === false/)
  assert.match(dock, /openSettings\('security'\)/)
  assert.match(dock, /passwordText\.setup\.promptStatus/)
  assert.match(settings, /uiStore\.settingsTab/)
})

test('first-time setup verifies identity then refreshes account state', async () => {
  const [component, authApi] = await Promise.all([
    source('components/settings/FirstTimePasswordSetupSettings.vue'),
    source('api/auth.js')
  ])

  assert.match(component, /autocomplete="one-time-code"/)
  assert.match(component, /autocomplete="new-password"/)
  assert.match(component, /authApi\.sendPasswordSetupCode/)
  assert.match(component, /authApi\.setupPassword/)
  assert.match(component, /authApi\.getProfile/)
  assert.match(component, /userStore\.setUser/)
  assert.ok(
    component.lastIndexOf("emit('completed')") <
      component.lastIndexOf('await refreshUser()')
  )
  assert.match(authApi, /password\/setup\/send-code/)
  assert.match(authApi, /password\/setup'/)
})
