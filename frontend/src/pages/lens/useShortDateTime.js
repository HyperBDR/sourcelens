import { useI18n } from 'vue-i18n'

/**
 * Short, localized MM/DD HH:mm formatter for Lens admin timestamps, with a
 * shared "not recorded" fallback for empty values.
 */
export function useShortDateTime() {
  const { locale, t } = useI18n()
  return (value) => {
    if (!value) {
      return t('lensAdmin.table.notRecorded')
    }
    return new Intl.DateTimeFormat(locale.value, {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    }).format(new Date(value))
  }
}
