const SENSITIVE_ENVIRONMENT_NAME =
  /(?:PASSWORD|PASSWD|TOKEN|SECRET|API_KEY|PRIVATE_KEY)$/i

export const SHELL_ENVIRONMENT_NAME_PATTERN = '[A-Z_][A-Z0-9_]*'

function isSensitiveEnvironmentName(value) {
  return SENSITIVE_ENVIRONMENT_NAME.test(String(value || ''))
}

export function buildSkillEnvironment(items = []) {
  return items.map((item) => {
    const name = (item.name || '').trim()
    return {
      name,
      description: (item.description || '').trim(),
      required: true,
      secret: !!item.secret || isSensitiveEnvironmentName(name)
    }
  })
}

export function skillEnvironmentForm(declarations = []) {
  return declarations.map((item) => ({
    name: item.name || '',
    description: item.description || '',
    required: true,
    secret: !!item.secret || isSensitiveEnvironmentName(item.name)
  }))
}
