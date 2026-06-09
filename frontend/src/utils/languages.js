import { SUPPORTED_UI_LANGUAGES } from '@/i18n'

const LANGUAGE_FLAGS = {
  en: '🇺🇸',
  'zh-CN': '🇨🇳'
}

export function getUiLanguageOptions(t) {
  return SUPPORTED_UI_LANGUAGES.map((language) => ({
    value: language,
    label: t(`settings.preferences.languages.${language}`),
    flag: LANGUAGE_FLAGS[language] || language.toUpperCase()
  }))
}

export function getUiLanguageLabel(language, t) {
  return t(`settings.preferences.languages.${language}`)
}
