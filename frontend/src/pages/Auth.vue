<template>
  <div
    class="flex min-h-screen items-center justify-center bg-surface-sunken px-4 py-12 sm:px-6 lg:px-8"
  >
    <div class="w-full max-w-md space-y-8">
      <!-- Header -->
      <div>
        <div class="mb-4 flex items-center justify-between gap-4">
          <BrandLogo variant="responsive" />
          <h2 class="text-2xl font-semibold text-ink-900">
            {{ t('auth.loginTitle') }}
          </h2>
          <LanguageSwitcher />
        </div>
      </div>

      <!-- Login Form -->
      <form class="mt-6 space-y-4" @submit.prevent="handleLogin">
        <div>
          <label class="mb-1 block text-sm font-medium text-ink-700">
            {{ t('auth.username') }}
          </label>
          <BaseInput
            v-model="formData.username"
            type="text"
            name="username"
            autocomplete="username"
            :placeholder="t('auth.username')"
            required
            :error="errors.username"
            :disabled="loading"
          />
        </div>

        <BaseInput
          v-model="formData.password"
          :label="t('auth.password')"
          type="password"
          name="password"
          autocomplete="current-password"
          :placeholder="t('auth.password')"
          required
          :error="errors.password"
          :disabled="loading"
        />

        <div class="flex items-center">
          <input
            id="remember-me"
            v-model="rememberMe"
            name="remember-me"
            type="checkbox"
            class="h-4 w-4 rounded border-line text-primary-600 focus:ring-primary-500"
          />
          <label for="remember-me" class="ml-2 block text-sm text-ink-900">
            {{ t('auth.rememberMe') }}
          </label>
        </div>

        <div
          v-if="errorMessage"
          class="rounded-lg border border-danger-100 bg-danger-50 p-4"
        >
          <p class="text-sm text-danger-700">
            {{ errorMessage }}
          </p>
        </div>

        <BaseButton
          type="submit"
          variant="primary"
          class="w-full"
          :loading="loading"
          :disabled="loading"
        >
          {{ loading ? t('auth.signingIn') : t('auth.signIn') }}
        </BaseButton>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/store/user'
import BaseInput from '@/components/ui/BaseInput.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import LanguageSwitcher from '@/components/ui/LanguageSwitcher.vue'
import BrandLogo from '@/components/layout/BrandLogo.vue'

const { t } = useI18n()
const router = useRouter()
const userStore = useUserStore()

const formData = reactive({
  username: '',
  password: ''
})

const errors = reactive({
  username: '',
  password: ''
})

const loading = ref(false)
const errorMessage = ref('')
const rememberMe = ref(false)

const validateLogin = () => {
  errors.username = ''
  errors.password = ''

  if (!formData.username.trim()) {
    errors.username = t('auth.required.username')
    return false
  }

  if (!formData.password) {
    errors.password = t('auth.required.password')
    return false
  }

  return true
}

const handleLogin = async () => {
  if (!validateLogin()) {
    return
  }

  loading.value = true
  errorMessage.value = ''

  try {
    await userStore.login({
      username: formData.username,
      password: formData.password
    })

    // Keep loading state during navigation to prevent button re-enabling
    // Wait for navigation to complete before clearing loading
    // If navigation succeeds, component will unmount, so loading will be cleared automatically
    try {
      await router.push(userStore.getUserLandingPath())
    } catch (navigationError) {
      // Navigation failed (e.g., route doesn't exist), clear loading
      console.error('Navigation error:', navigationError)
      loading.value = false
    }
    // If navigation succeeds, component unmounts and loading is cleared automatically
  } catch (error) {
    console.error('Login error:', error)
    errorMessage.value = t('auth.loginError')
    // Only clear loading on error
    loading.value = false
  }
}
</script>
