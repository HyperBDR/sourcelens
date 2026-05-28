import { createI18n } from 'vue-i18n'

import en from '../locales/en.json'
import zhCN from '../locales/zh-CN.json'
import adminEn from '../admin/locales/en.json'
import adminZhCN from '../admin/locales/zh-CN.json'

export const SUPPORTED_UI_LANGUAGES = ['en', 'zh-CN']

const isPlainObject = (value) =>
  value !== null && typeof value === 'object' && !Array.isArray(value)

const deepMergeMessages = (base, extra) => {
  const output = { ...base }

  Object.entries(extra).forEach(([key, value]) => {
    if (isPlainObject(value) && isPlainObject(output[key])) {
      output[key] = deepMergeMessages(output[key], value)
      return
    }
    output[key] = value
  })

  return output
}

export const normalizeUiLanguage = (language) =>
  SUPPORTED_UI_LANGUAGES.includes(language) ? language : 'en'

// Get language from localStorage or default to 'en'.
const getStoredLanguage = () => {
  const stored = localStorage.getItem('userLanguage')
  const normalized = normalizeUiLanguage(stored)

  if (stored && stored !== normalized) {
    localStorage.setItem('userLanguage', normalized)
  }

  return normalized
}

// Create Vue i18n instance
const i18n = createI18n({
  legacy: false,
  locale: getStoredLanguage(),
  fallbackLocale: 'en',
  messages: {
    en: deepMergeMessages(en, adminEn),
    'zh-CN': deepMergeMessages(zhCN, adminZhCN)
  }
})

export default i18n
