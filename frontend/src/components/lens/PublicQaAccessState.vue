<template>
  <div class="rounded-lg border border-line bg-surface px-5 py-14 text-center">
    <div
      v-if="type === 'login-required'"
      class="mx-auto flex max-w-md flex-col items-center"
    >
      <div
        class="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-primary-50 text-primary-600"
      >
        <LockKeyhole :size="22" :stroke-width="2" aria-hidden="true" />
      </div>
      <h1 class="text-lg font-semibold text-ink-900">
        {{ t('lens.qa.loginRequiredTitle') }}
      </h1>
      <p class="mt-2 text-sm leading-6 text-ink-500">
        {{ t('lens.qa.loginRequiredDescription') }}
      </p>
      <div class="mt-6 flex flex-wrap justify-center gap-3">
        <BaseButton variant="primary" @click="$emit('login')">
          {{ t('lens.qa.loginToContinue') }}
        </BaseButton>
        <BaseButton variant="secondary" @click="$emit('home')">
          {{ t('lens.qa.returnHome') }}
        </BaseButton>
      </div>
    </div>

    <p v-else class="text-sm font-medium text-ink-500">
      {{ t('lens.qa.notFound') }}
    </p>
  </div>
</template>

<script setup>
import { LockKeyhole } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import BaseButton from '@/components/ui/BaseButton.vue'

defineProps({
  type: {
    type: String,
    default: 'not-found',
    validator: (value) => ['not-found', 'login-required'].includes(value)
  }
})

defineEmits(['login', 'home'])

const { t } = useI18n()
</script>
