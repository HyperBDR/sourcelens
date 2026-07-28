export const passwordManagementMessages = {
  en: {
    passwordManagement: {
      forgot: {
        link: 'Forgot password?',
        title: 'Reset your password',
        description: 'Enter your account email to receive a reset link.',
        email: 'Email address',
        emailPlaceholder: 'Enter your email address',
        required: 'Email address is required',
        invalid: 'Enter a valid email address',
        submit: 'Send reset link',
        sending: 'Sending...',
        success:
          'If an eligible account exists for this email, a reset link has been sent.',
        error: 'Unable to request a reset link. Please try again.',
        back: 'Back to password login'
      },
      security: {
        title: 'Security',
        description: 'Change the password used to sign in to this account.',
        unavailable:
          'This account does not have a local password that can be changed here.',
        currentPassword: 'Current password',
        newPassword: 'New password',
        confirmPassword: 'Confirm new password',
        currentRequired: 'Enter your current password',
        newRequired: 'Enter a new password',
        confirmRequired: 'Confirm your new password',
        mismatch: 'Passwords do not match',
        wrongCurrent: 'Current password is incorrect',
        submit: 'Change password',
        changing: 'Changing...',
        success: 'Password changed successfully',
        error: 'Unable to change password. Please try again.',
        forgotPassword: 'Forgot your current password?',
        backToSecurity: 'Back to security'
      },
      policy: {
        tooShort: 'Password must be at least 8 characters long',
        tooLong: 'Password cannot exceed 32 characters',
        requirements: 'Password must contain both letters and numbers'
      }
    }
  },
  'zh-CN': {
    passwordManagement: {
      forgot: {
        link: '忘记密码？',
        title: '找回密码',
        description: '输入账户邮箱，我们会向符合条件的账户发送重置链接。',
        email: '邮箱地址',
        emailPlaceholder: '请输入邮箱地址',
        required: '请输入邮箱地址',
        invalid: '请输入有效的邮箱地址',
        submit: '发送重置链接',
        sending: '正在发送...',
        success: '如果该邮箱存在符合条件的账户，重置链接已经发送。',
        error: '暂时无法请求重置链接，请重试。',
        back: '返回密码登录'
      },
      security: {
        title: '安全',
        description: '修改用于登录当前账户的密码。',
        unavailable: '此账户没有可在这里修改的本地密码。',
        currentPassword: '当前密码',
        newPassword: '新密码',
        confirmPassword: '确认新密码',
        currentRequired: '请输入当前密码',
        newRequired: '请输入新密码',
        confirmRequired: '请再次输入新密码',
        mismatch: '两次输入的密码不一致',
        wrongCurrent: '当前密码不正确',
        submit: '修改密码',
        changing: '正在修改...',
        success: '密码修改成功',
        error: '暂时无法修改密码，请重试。',
        forgotPassword: '忘记当前密码？',
        backToSecurity: '返回安全设置'
      },
      policy: {
        tooShort: '密码至少需要 8 个字符',
        tooLong: '密码不能超过 32 个字符',
        requirements: '密码必须同时包含字母和数字'
      }
    }
  }
}

export function getPasswordManagementText(locale) {
  const key = String(locale || '')
    .toLowerCase()
    .startsWith('zh')
    ? 'zh-CN'
    : 'en'
  return passwordManagementMessages[key].passwordManagement
}
