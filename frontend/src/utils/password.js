export function getPasswordPolicyError(password) {
  if (password.length < 8) return 'tooShort'
  if (password.length > 32) return 'tooLong'
  if (!/[a-zA-Z]/.test(password) || !/[0-9]/.test(password)) {
    return 'requirements'
  }
  return ''
}

const PASSWORD_SETUP_ERROR_KEYS = {
  DELIVERY_FAILED: 'deliveryFailed',
  EXPIRED: 'codeExpired',
  INVALID: 'codeInvalid',
  PASSWORD_ALREADY_SET: 'alreadySet',
  RATE_LIMITED: 'rateLimited',
  TOO_MANY_ATTEMPTS: 'tooManyAttempts'
}

export function getPasswordSetupErrorKey(errorCode) {
  return (
    PASSWORD_SETUP_ERROR_KEYS[String(errorCode || '').toUpperCase()] || 'error'
  )
}

export function getApiErrorData(error) {
  const responseData = error?.response?.data
  return responseData?.data || responseData || {}
}

export function getFirstApiError(error) {
  const data = getApiErrorData(error)
  const errors = data.errors || data
  const directMessage = data.error || data.detail || data.message

  if (typeof directMessage === 'string') return directMessage
  if (!errors || typeof errors !== 'object') return ''

  for (const value of Object.values(errors)) {
    if (typeof value === 'string') return value
    if (Array.isArray(value) && value.length) return String(value[0])
  }
  return ''
}
