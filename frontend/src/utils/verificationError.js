const ERROR_TRANSLATIONS = {
  INVALID: 'auth.codeLogin.invalidCode',
  EXPIRED: 'auth.codeLogin.expiredCode',
  TOO_MANY_ATTEMPTS: 'auth.codeLogin.tooManyAttempts'
}

export const getVerificationErrorMessage = (error, translate) => {
  const response = error?.response?.data || {}
  const details = response?.data || response
  const errorCode = details?.error_code || response?.error_code

  if (ERROR_TRANSLATIONS[errorCode]) {
    return translate(ERROR_TRANSLATIONS[errorCode])
  }

  return translate('auth.codeLogin.verifyFailed')
}
