<template>
  <div
    class="flex min-h-screen items-center justify-center bg-surface-sunken px-4 py-12 sm:px-6 lg:px-8"
  >
    <div class="w-full max-w-sm">
      <div class="mb-3 flex justify-end">
        <LanguageSwitcher />
      </div>

      <!-- Login card -->
      <div class="rounded-2xl border border-line bg-white p-8 shadow-xl">
        <div class="mb-7 text-center">
          <BrandLogo
            variant="mark"
            class="mx-auto mb-4 flex h-8 justify-center"
          />
          <h1 class="text-xl font-semibold text-ink-900">
            {{ t('auth.loginTitle') }}
          </h1>
          <p class="mt-2 text-sm text-ink-500">
            {{ t('auth.codeLogin.modalSubtitle') }}
          </p>
        </div>

        <LoginForm @success="redirectAfterLogin" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/store/user'
import LanguageSwitcher from '@/components/ui/LanguageSwitcher.vue'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import LoginForm from '@/components/auth/LoginForm.vue'

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const redirectAfterLogin = async () => {
  const next = route.query.next
  if (typeof next === 'string' && next.startsWith('/')) {
    await navigate(next)
    return
  }
  // Every authenticated user lands on '/', where Home resolves a default
  // assistant and enters chat (or shows a role-aware empty state).
  await navigate(userStore.getUserLandingPath())
}

const navigate = async (target) => {
  try {
    await router.replace(target)
  } catch (navigationError) {
    console.error('Navigation error:', navigationError)
  }
}
</script>
