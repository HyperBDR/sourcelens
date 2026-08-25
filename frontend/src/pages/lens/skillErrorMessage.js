import { extractErrorMessage } from '../../utils/api.js'

const EXACT_ERROR_KEYS = {
  'Skill is still bound to assistants.': 'skillBound',
  'Skill name confirmation does not match.': 'confirmationMismatch',
  'Skill package file is required.': 'packageFileRequired',
  'Skill package exceeds 50 MB.': 'packageTooLarge',
  'Skill package must be a .zip file.': 'packageZipRequired',
  'Skill package must be a valid zip archive.': 'packageInvalidZip',
  'Skill source type cannot be changed during update.': 'sourceTypeMismatch',
  'Updated package Skill name must match the existing Skill.':
    'updatedNameMismatch',
  'GitHub skill package exceeds 50 MB.': 'githubPackageTooLarge',
  'Skill package contains too many files.': 'packageTooManyFiles',
  'Skill package contains an oversized file.': 'packageFileTooLarge',
  'Skill package unpacks over 100 MB.': 'packageUnpackedTooLarge',
  'Skill package contains unsafe paths.': 'packageUnsafePaths',
  'Skill package contains blocked directories.': 'packageBlockedDirectories',
  'Skill package contains unsupported file types.':
    'packageUnsupportedFileTypes',
  'Skill package must contain one SKILL.md root.': 'packageRootInvalid',
  'SKILL.md exceeds 256 KB.': 'skillMdTooLarge',
  'SKILL.md must start with YAML frontmatter.': 'skillMdFrontmatterRequired',
  'SKILL.md frontmatter is not closed.': 'skillMdFrontmatterUnclosed',
  'SKILL.md requires name and description.': 'skillMdMetadataRequired',
  'sourcelens.json must contain valid JSON.': 'configJsonInvalid',
  'sourcelens.json must contain a JSON object.': 'configJsonObjectRequired',
  "Skill name must use lowercase letters, numbers, '-' or '_'.":
    'skillNameInvalid',
  'GitHub URL is required.': 'githubUrlRequired',
  'Only public GitHub URLs are supported.': 'githubPublicOnly',
  'GitHub URL must include owner and repository.': 'githubRepositoryRequired',
  'GitHub download redirected to an unsafe host.': 'githubUnsafeRedirect',
  'GitHub repository must publish a tag before it can be imported.':
    'githubTagRequired',
  'Environment variables must be valid JSON.': 'environmentInvalid',
  'Skill generator model is not configured.': 'generatorNotConfigured'
}

const ERROR_RULES = [
  [/^GitHub download failed:/, 'githubDownloadFailed'],
  [
    /^(Skill transforms|A Skill may declare at most 32 transforms|Transform names|Transform ')/,
    'transformInvalid'
  ],
  [
    /^(The Skill API|Each Skill API|Skill API routes|"[^"]+" is not an allowed API method)/,
    'apiPolicyInvalid'
  ],
  [
    /^(Environment variables|Environment variable names|Each environment variable|Each entry must include a variable name|The value for |"[^"]+" is not a valid environment variable name)/,
    'environmentInvalid'
  ],
  [/^Skill package /, 'packageInvalid'],
  [/^SKILL\.md /, 'skillMdInvalid'],
  [/^GitHub /, 'githubInvalid']
]

function errorKey(message) {
  if (EXACT_ERROR_KEYS[message]) {
    return EXACT_ERROR_KEYS[message]
  }
  return ERROR_RULES.find(([pattern]) => pattern.test(message))?.[1] || ''
}

export function skillErrorMessage(error, t, fallback) {
  const message = extractErrorMessage(error, fallback)
  if (!error?.response?.data) {
    return message
  }
  const key = errorKey(message)
  return key ? t(`lensAdmin.skills.errors.${key}`) : fallback
}
