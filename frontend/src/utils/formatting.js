import { format } from 'date-fns'

/**
 * Locale-aware number format (integer, no decimals). For LLM stats/usage.
 * @param {number|null|undefined} value
 * @param {string} locale - BCP 47 locale (e.g. from useI18n().locale.value)
 * @returns {string}
 */
export function formatNumLocale(value, locale) {
  if (value === null || value === undefined) return '-'
  const n = Number(value)
  if (Number.isNaN(n)) return '-'
  return new Intl.NumberFormat(locale, {
    maximumFractionDigits: 0,
    minimumFractionDigits: 0
  }).format(n)
}

/**
 * Locale-aware cost format with currency. For LLM stats/usage.
 * @param {number|null|undefined} value
 * @param {string} currency - Currency code (default 'USD')
 * @param {string} locale - BCP 47 locale
 * @returns {string}
 */
export function formatCostLocale(value, currency = 'USD', locale = 'en') {
  if (value === null || value === undefined) return '-'
  const n = Number(value)
  if (Number.isNaN(n)) return '-'
  const code = (currency || 'USD').toUpperCase()
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency: code,
    minimumFractionDigits: 4,
    maximumFractionDigits: 6
  }).format(n)
}

/**
 * Format ISO date string to locale string (date + time). For LLM usage list.
 * @param {string} iso - ISO 8601 date string
 * @param {string} locale - BCP 47 locale
 * @returns {string}
 */
export function formatDateIsoLocale(iso, locale = 'en') {
  if (!iso) return '-'
  try {
    return new Date(iso).toLocaleString(locale)
  } catch {
    return iso
  }
}

/**
 * Format cost with currency symbol
 * @param {number|null|undefined} cost - The cost value
 * @param {string} currency - Currency code (default: 'CNY')
 * @returns {string} Formatted cost string
 */
export function formatCost(cost, currency = 'CNY') {
  if (cost === null || cost === undefined) return '-'
  const symbol = currency === 'CNY' ? '¥' : '$'
  return `${symbol}${Number(cost).toFixed(2)}`
}

/**
 * Format percentage change
 * @param {number|null|undefined} change - The percentage change value
 * @returns {string} Formatted change string with sign
 */
export function formatChange(change) {
  if (change === null || change === undefined) return '-'
  const sign = change >= 0 ? '+' : ''
  return `${sign}${Number(change).toFixed(2)}%`
}

/**
 * Format date string to readable format
 * @param {string|Date} dateString - Date string or Date object
 * @param {string} pattern - Date format pattern (default: 'yyyy-MM-dd HH:mm')
 * @returns {string} Formatted date string
 */
export function formatDate(dateString, pattern = 'yyyy-MM-dd HH:mm') {
  if (!dateString) return '-'
  try {
    const date =
      typeof dateString === 'string' ? new Date(dateString) : dateString
    return format(date, pattern)
  } catch {
    return dateString
  }
}

/**
 * Format duration in seconds to human-readable string with 2 decimal places for numeric parts.
 * @param {number|null|undefined} seconds - Duration in seconds
 * @returns {string} e.g. "12.35s", "1m 45.68s", "2h 30.50m"
 */
export function formatDuration(seconds) {
  if (seconds == null || seconds === '') return '-'
  const s = Number(seconds)
  if (Number.isNaN(s)) return '-'
  if (s < 60) return `${s.toFixed(2)}s`
  if (s < 3600) {
    const m = Math.floor(s / 60)
    const sec = s % 60
    return `${m}m ${sec.toFixed(2)}s`
  }
  const h = Math.floor(s / 3600)
  const min = (s % 3600) / 60
  return `${h}h ${min.toFixed(2)}m`
}

/**
 * Get CSS class for change value (positive/negative)
 * @param {number|null|undefined} change - The change value
 * @param {string} defaultClass - Default class when change is null/undefined (default: 'text-gray-500')
 * @param {boolean} includeFontMedium - Whether to include 'font-medium' class (default: false)
 * @returns {string} CSS class string
 */
export function getChangeClass(
  change,
  defaultClass = 'text-gray-500',
  includeFontMedium = false
) {
  if (change === null || change === undefined) return defaultClass
  const baseClass = change >= 0 ? 'text-red-600' : 'text-green-600'
  return includeFontMedium ? `${baseClass} font-medium` : baseClass
}
