<template>
  <div class="space-y-4">
    <p class="text-sm text-gray-500">
      {{ t('settings.modal.notificationsDesc') }}
    </p>
    <div class="rounded-xl border border-line">
      <div class="flex items-start justify-between gap-4 px-4 py-4">
        <div class="min-w-0">
          <div class="text-sm font-medium text-gray-900">
            {{ t('settings.modal.completionIndicator') }}
          </div>
          <p class="mt-1 text-xs leading-5 text-gray-500">
            {{ t('settings.modal.completionIndicatorDesc') }}
          </p>
        </div>
        <button
          type="button"
          role="switch"
          :aria-checked="preferencesStore.answerCompletionIndicator"
          :aria-label="t('settings.modal.completionIndicator')"
          class="notification-switch focus:ring-primary-200"
          :class="
            preferencesStore.answerCompletionIndicator
              ? 'bg-primary-600'
              : 'bg-gray-200'
          "
          @click="toggleCompletionIndicator"
        >
          <span
            class="notification-switch-knob"
            :class="
              preferencesStore.answerCompletionIndicator
                ? 'translate-x-[22px]'
                : 'translate-x-0.5'
            "
          />
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

import { usePreferencesStore } from '@/store/preferences'

const { t } = useI18n()
const preferencesStore = usePreferencesStore()

function toggleCompletionIndicator() {
  preferencesStore.setAnswerCompletionIndicator(
    !preferencesStore.answerCompletionIndicator
  )
}
</script>

<style scoped>
.notification-switch {
  @apply relative mt-0.5 inline-flex h-6 w-11 shrink-0 rounded-full;
  @apply transition-colors focus:outline-none focus:ring-2 focus:ring-offset-2;
}

.notification-switch-knob {
  @apply pointer-events-none inline-block h-5 w-5 translate-y-0.5;
  @apply rounded-full bg-white shadow-sm transition-transform;
}
</style>
