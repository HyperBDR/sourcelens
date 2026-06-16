<template>
  <div class="onboarding">
    <div class="onboarding-card">
      <div
        class="onboarding-badge"
        :class="variant === 'admin' ? 'badge-admin' : 'badge-visitor'"
      >
        <Sparkles
          v-if="variant === 'admin'"
          :size="28"
          :stroke-width="1.75"
          aria-hidden="true"
        />
        <img
          v-else
          src="/brand/logo_transparent.png"
          alt=""
          class="badge-logo"
        />
      </div>
      <h1 class="onboarding-title">{{ title }}</h1>
      <p class="onboarding-subtitle">{{ subtitle }}</p>
      <div v-if="variant === 'admin'" class="onboarding-actions">
        <BaseButton variant="primary" size="lg" @click="goCreate">
          <Plus :size="18" :stroke-width="2.25" aria-hidden="true" />
          {{ t('lens.onboarding.createButton') }}
        </BaseButton>
        <button type="button" class="onboarding-link" @click="goConsole">
          {{ t('lens.onboarding.openConsole') }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Plus, Sparkles } from '@lucide/vue'

import BaseButton from '@/components/ui/BaseButton.vue'

const props = defineProps({
  variant: {
    type: String,
    default: 'visitor',
    validator: (value) => ['admin', 'visitor'].includes(value)
  }
})

const router = useRouter()
const { t } = useI18n()

const title = computed(() =>
  props.variant === 'admin'
    ? t('lens.onboarding.title')
    : t('lens.onboarding.visitorTitle')
)

const subtitle = computed(() =>
  props.variant === 'admin'
    ? t('lens.onboarding.subtitle')
    : t('lens.onboarding.visitorSubtitle')
)

function goCreate() {
  router.push('/management/lens/assistants?create=1')
}

function goConsole() {
  router.push('/management/lens/assistants')
}
</script>

<style scoped>
.onboarding {
  @apply flex h-full w-full items-center justify-center px-6 py-12;
}

.onboarding-card {
  @apply flex w-full max-w-md flex-col items-center text-center;
}

.onboarding-badge {
  @apply mb-6 flex h-16 w-16 items-center justify-center rounded-2xl;
}

.badge-admin {
  @apply bg-primary-50 text-primary-600;
}

.badge-visitor {
  @apply border border-line bg-surface-sunken;
}

.badge-logo {
  @apply h-8 w-8 object-contain opacity-80;
}

.onboarding-title {
  @apply text-2xl font-semibold text-ink-900;
}

.onboarding-subtitle {
  @apply mt-3 text-sm leading-6 text-ink-500;
}

.onboarding-actions {
  @apply mt-8 flex flex-col items-center gap-3;
}

.onboarding-link {
  @apply text-sm font-medium text-ink-500 transition-colors hover:text-ink-700;
}
</style>
