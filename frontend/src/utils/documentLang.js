const SUPPORTED_UI_LANGUAGES = ['en', 'zh-CN']

export const toDocumentLang = (language) => {
  const normalized = SUPPORTED_UI_LANGUAGES.includes(language) ? language : 'en'
  return normalized === 'zh-CN' ? 'zh-CN' : 'en-US'
}
