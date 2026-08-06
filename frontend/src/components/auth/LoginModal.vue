<template>
  <Teleport to="body">
    <Transition name="login">
      <div v-if="show" class="login-overlay" @click.self="$emit('close')">
        <div class="login-card">
          <button
            type="button"
            class="login-close"
            :aria-label="t('common.close')"
            @click="$emit('close')"
          >
            <svg
              class="h-5 w-5"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                d="M6 18L18 6M6 6l12 12"
              />
            </svg>
          </button>

          <div class="login-head">
            <BrandLogo variant="mark" class="login-logo" />
            <h2 class="login-title">{{ t('auth.login') }}</h2>
            <p class="login-sub">{{ t('auth.codeLogin.modalSubtitle') }}</p>
          </div>

          <LoginForm @success="$emit('success')" />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import LoginForm from '@/components/auth/LoginForm.vue'

defineProps({
  show: {
    type: Boolean,
    default: false
  }
})

defineEmits(['close', 'success'])

const { t } = useI18n()
</script>

<style scoped>
.login-overlay {
  @apply fixed inset-0 z-[60] flex items-center justify-center p-4;
  background: rgba(17, 24, 39, 0.5);
  backdrop-filter: blur(4px);
}

.login-card {
  @apply relative w-full max-w-sm rounded-2xl bg-surface p-8;
  box-shadow:
    0 20px 50px -12px rgba(0, 0, 0, 0.3),
    0 0 0 1px rgba(0, 0, 0, 0.04);
}

.login-close {
  @apply absolute right-3.5 top-3.5 rounded-lg p-1.5 text-theme-subtle transition-colors hover:bg-surface-hover hover:text-theme-secondary;
}

.login-head {
  @apply mb-7 text-center;
}

.login-logo {
  @apply mx-auto mb-4 flex h-8 justify-center;
}

.login-title {
  @apply text-xl font-semibold text-theme;
}

.login-sub {
  @apply mx-auto mt-2 max-w-[16rem] text-sm leading-relaxed text-theme-muted;
}

.login-enter-active,
.login-leave-active {
  transition: opacity 0.2s ease;
}

.login-enter-from,
.login-leave-to {
  opacity: 0;
}

.login-enter-active .login-card,
.login-leave-active .login-card {
  transition:
    transform 0.24s cubic-bezier(0.16, 1, 0.3, 1),
    opacity 0.24s ease;
}

.login-enter-from .login-card,
.login-leave-to .login-card {
  opacity: 0;
  transform: translateY(12px) scale(0.97);
}
</style>
