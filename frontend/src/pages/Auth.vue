<template>
  <div
    class="flex min-h-screen items-center justify-center bg-surface-sunken px-4 py-12 sm:px-6 lg:px-8"
  >
    <div class="w-full max-w-sm">
      <div class="mb-3 flex justify-end">
        <LanguageSwitcher />
      </div>

      <!-- Login card -->
      <div
        v-if="!noAssistant"
        class="rounded-2xl border border-line bg-white p-8 shadow-xl"
      >
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

      <!-- Signed in but no assistant available (direct /login entry) -->
      <div
        v-else
        class="rounded-2xl border border-line bg-white p-8 text-center shadow-xl"
      >
        <BrandLogo
          variant="mark"
          class="mx-auto mb-4 flex h-8 justify-center"
        />
        <h1 class="text-xl font-semibold text-ink-900">
          {{ t('auth.noAssistant.title') }}
        </h1>
        <p class="mt-3 text-sm leading-relaxed text-ink-500">
          {{ t('auth.noAssistant.message') }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
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

const noAssistant = ref(false)

const redirectAfterLogin = async () => {
  const next = route.query.next
  if (typeof next === 'string' && next.startsWith('/')) {
    await navigate(next)
    return
  }
  // Admins reach their console; regular end-users have no home here and
  // should enter via a shared assistant link instead.
  if (userStore.userHasFeature('admin_console')) {
    await navigate(userStore.getUserLandingPath())
    return
  }
  noAssistant.value = true
}

const navigate = async (target) => {
  try {
    await router.replace(target)
  } catch (navigationError) {
    console.error('Navigation error:', navigationError)
  }
}
</script>
