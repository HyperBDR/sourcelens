const SUPPORTED_UI_LANGUAGES = ['en', 'zh-CN', 'es']

export const toDocumentLang = (language) => {
  const normalized = SUPPORTED_UI_LANGUAGES.includes(language) ? language : 'en'
  if (normalized === 'zh-CN') return 'zh-CN'
  return normalized === 'es' ? 'es' : 'en-US'
}
