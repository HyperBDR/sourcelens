<template>
  <router-link
    :to="`/lens/qa/${item.token}`"
    class="block rounded-lg border border-line bg-surface px-4 py-3 no-underline transition-colors hover:bg-surface-sunken"
  >
    <div class="line-clamp-2 text-sm font-medium text-ink-900">
      {{ item.title }}
    </div>
    <p
      v-if="item.answer_snippet"
      class="mt-1 line-clamp-2 text-sm text-ink-500"
    >
      {{ item.answer_snippet }}
    </p>
    <p v-if="languageMismatch" class="mt-1 text-xs text-ink-400">
      {{
        t('lens.qa.contentLanguageNotice', { language: contentLanguageLabel })
      }}
    </p>
    <div class="mt-2 flex items-center gap-3 text-xs text-ink-400">
      <span>{{ formatDate(item.published_at, 'yyyy-MM-dd HH:mm') }}</span>
      <span>{{ t('lens.qa.viewCount', { count: item.view_count }) }}</span>
    </div>
  </router-link>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { formatDate } from '@/utils/formatting'

const props = defineProps({ item: { type: Object, required: true } })

const { t, locale } = useI18n()
const contentLanguage = computed(() => props.item.content_language || '')
const contentLanguageKey = computed(() =>
  contentLanguage.value.startsWith('zh')
    ? 'zh-CN'
    : contentLanguage.value.startsWith('es')
      ? 'es'
      : 'en'
)
const contentLanguageLabel = computed(() =>
  contentLanguage.value
    ? t(`settings.preferences.languages.${contentLanguageKey.value}`)
    : ''
)
const languageMismatch = computed(
  () =>
    Boolean(contentLanguage.value) &&
    contentLanguage.value.split('-')[0] !== locale.value.split('-')[0]
)
</script>
