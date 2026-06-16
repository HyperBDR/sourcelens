<template>
  <div class="onboarding">
    <!-- Admin: a three-step setup guide instead of a bare empty frame. -->
    <div v-if="variant === 'admin'" class="onboarding-card onboarding-card-wide">
      <div class="onboarding-badge badge-admin">
        <Sparkles :size="28" :stroke-width="1.75" aria-hidden="true" />
      </div>
      <h1 class="onboarding-title">{{ t('lens.onboarding.title') }}</h1>
      <p class="onboarding-subtitle">{{ t('lens.onboarding.subtitle') }}</p>

      <div class="steps">
        <div class="step">
          <div class="step-icon">
            <Database :size="24" :stroke-width="1.75" aria-hidden="true" />
            <span class="step-num">1</span>
          </div>
          <div class="step-title">{{ t('lens.onboarding.step1Title') }}</div>
          <div class="step-desc">{{ t('lens.onboarding.step1Desc') }}</div>
        </div>

        <div class="step-arrow" aria-hidden="true">
          <ArrowRight :size="18" :stroke-width="2" />
        </div>

        <div class="step">
          <div class="step-icon">
            <Bot :size="24" :stroke-width="1.75" aria-hidden="true" />
            <span class="step-num">2</span>
          </div>
          <div class="step-title">{{ t('lens.onboarding.step2Title') }}</div>
          <div class="step-desc">{{ t('lens.onboarding.step2Desc') }}</div>
        </div>

        <div class="step-arrow" aria-hidden="true">
          <ArrowRight :size="18" :stroke-width="2" />
        </div>

        <div class="step">
          <div class="step-icon">
            <MessageSquare :size="24" :stroke-width="1.75" aria-hidden="true" />
            <span class="step-num">3</span>
          </div>
          <div class="step-title">{{ t('lens.onboarding.step3Title') }}</div>
          <div class="step-desc">{{ t('lens.onboarding.step3Desc') }}</div>
        </div>
      </div>

      <div class="onboarding-cta">
        <BaseButton variant="primary" size="lg" @click="goConsole">
          {{ t('lens.onboarding.enterConsole') }}
        </BaseButton>
      </div>
    </div>

    <!-- Visitor / end-user: a simple no-assistant notice. -->
    <div v-else class="onboarding-card">
      <div class="onboarding-badge badge-visitor">
        <img src="/brand/logo_transparent.png" alt="" class="badge-logo" />
      </div>
      <h1 class="onboarding-title">{{ t('lens.onboarding.visitorTitle') }}</h1>
      <p class="onboarding-subtitle">
        {{ t('lens.onboarding.visitorSubtitle') }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ArrowRight, Bot, Database, MessageSquare, Sparkles } from '@lucide/vue'

import BaseButton from '@/components/ui/BaseButton.vue'

defineProps({
  variant: {
    type: String,
    default: 'visitor',
    validator: (value) => ['admin', 'visitor'].includes(value)
  }
})

const router = useRouter()
const { t } = useI18n()

function goConsole() {
  // Enter the Lens admin console at step one (data sources); creating an
  // assistant before any source exists is not useful.
  router.push('/management/lens/datasources')
}
</script>

<style scoped>
.onboarding {
  @apply flex h-full w-full items-center justify-center px-6 py-12;
}

.onboarding-card {
  @apply flex w-full max-w-md flex-col items-center text-center;
}

.onboarding-card-wide {
  @apply max-w-2xl;
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

.steps {
  @apply mt-8 flex w-full flex-col items-stretch gap-3 sm:flex-row sm:items-center;
}

.step {
  @apply flex flex-1 flex-col items-center rounded-xl border border-line bg-surface px-4 py-5 text-center;
}

.step-icon {
  @apply relative mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-primary-50 text-primary-600;
}

.step-num {
  @apply absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-primary-600 text-[11px] font-semibold text-white;
}

.step-title {
  @apply text-sm font-semibold text-ink-900;
}

.step-desc {
  @apply mt-1 text-xs leading-5 text-ink-500;
}

.step-arrow {
  @apply hidden shrink-0 items-center justify-center text-ink-300 sm:flex;
}

.onboarding-cta {
  @apply mt-8;
}
</style>
