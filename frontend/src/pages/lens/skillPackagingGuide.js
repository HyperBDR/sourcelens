import { copyToClipboard } from '../../utils/clipboard.js'

export function buildSkillPackagingPrompt(base, transformContract) {
  return [base, transformContract].filter(Boolean).join('\n\n')
}

export async function copySkillPackagingPrompt(prompt, copy = copyToClipboard) {
  return copy(prompt)
}
