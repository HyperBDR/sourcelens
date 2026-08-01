import { SUPPORTED_UI_LANGUAGES } from '@/i18n'

const LANGUAGE_FLAGS = {
  en: '🇺🇸',
  'en-US': '🇺🇸',
  'zh-CN': '🇨🇳'
}

const ANSWER_LANGUAGES = ['en-US', 'zh-CN']

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

export function getAnswerLanguageOptions(t) {
  return ANSWER_LANGUAGES.map((language) => ({
    value: language,
    label: t(`settings.preferences.languages.${language}`),
    flag: LANGUAGE_FLAGS[language]
  }))
}
