export const MAX_SKILL_PACKAGE_BYTES = 50 * 1024 * 1024

export function skillPackageValidationError(file) {
  const name = String(file?.name || '').toLowerCase()
  if (!name.endsWith('.zip')) {
    return 'packageFileInvalidType'
  }
  if (Number(file?.size || 0) > MAX_SKILL_PACKAGE_BYTES) {
    return 'packageFileTooLarge'
  }
  return ''
}
