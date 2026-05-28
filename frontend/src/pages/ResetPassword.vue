<template>
  <div
    class="min-h-screen flex items-center justify-center bg-gray-50 px-4 py-12"
  >
    <div
      class="w-full max-w-md rounded-xl border border-gray-200 bg-white p-8 shadow-sm"
    >
      <div class="mb-6 text-center">
        <h1 class="text-2xl font-semibold text-gray-900">
          {{ t('password.reset.title') }}
        </h1>
        <p class="mt-2 text-sm text-gray-500">
          {{ t('password.reset.subtitle') }}
        </p>
      </div>

      <div
        v-if="successMessage"
        class="mb-4 rounded-md border border-green-200 bg-green-50 p-4 text-sm text-green-700"
      >
        <p class="font-medium text-green-800">
          {{ t('password.reset.successTitle') }}
        </p>
        <p class="mt-1">
          {{ successMessage }}
        </p>
      </div>

      <div
        v-if="errorMessage"
        class="mb-4 rounded-md border border-red-200 bg-red-50 p-4 text-sm text-red-700"
      >
        {{ errorMessage }}
      </div>

      <form
        v-if="!resetComplete"
        class="space-y-4"
        @submit.prevent="handleSubmit"
      >
        <BaseInput
          v-model="form.newPassword1"
          :label="t('password.reset.newPassword')"
          type="password"
          autocomplete="new-password"
          :placeholder="t('password.reset.newPasswordPlaceholder')"
          :error="fieldErrors.newPassword1"
          :disabled="submitting"
          required
        />

        <BaseInput
          v-model="form.newPassword2"
          :label="t('password.reset.confirmPassword')"
          type="password"
          autocomplete="new-password"
          :placeholder="t('password.reset.confirmPasswordPlaceholder')"
          :error="fieldErrors.newPassword2"
          :disabled="submitting"
          required
        />

        <BaseButton
          type="submit"
          variant="primary"
          class="w-full"
          :loading="submitting"
          :disabled="submitting"
        >
          {{ submitting ? t('common.loading') : t('password.reset.submit') }}
        </BaseButton>
      </form>

      <BaseButton
        v-else
        variant="primary"
        class="w-full"
        @click="router.push('/login')"
      >
        {{ t('password.reset.backToLogin') }}
      </BaseButton>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { authApi } from '@/api/auth'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const form = reactive({
  newPassword1: '',
  newPassword2: ''
})

const fieldErrors = reactive({
  newPassword1: '',
  newPassword2: ''
})

const submitting = ref(false)
const errorMessage = ref('')
const successMessage = ref('')
const resetComplete = ref(false)

const validateForm = () => {
  fieldErrors.newPassword1 = ''
  fieldErrors.newPassword2 = ''
  errorMessage.value = ''

  if (!form.newPassword1) {
    fieldErrors.newPassword1 = t('password.reset.newPasswordRequired')
  }

  if (!form.newPassword2) {
    fieldErrors.newPassword2 = t('password.reset.confirmPasswordRequired')
  }

  if (fieldErrors.newPassword1 || fieldErrors.newPassword2) {
    return false
  }

  if (form.newPassword1 !== form.newPassword2) {
    fieldErrors.newPassword2 = t('password.reset.passwordMismatch')
    return false
  }

  if (form.newPassword1.length < 8) {
    fieldErrors.newPassword1 = t('password.reset.passwordTooShort')
    return false
  }

  if (form.newPassword1.length > 32) {
    fieldErrors.newPassword1 = t('password.reset.passwordTooLong')
    return false
  }

  if (!/[a-zA-Z]/.test(form.newPassword1) || !/[0-9]/.test(form.newPassword1)) {
    fieldErrors.newPassword1 = t('password.reset.passwordRequirements')
    return false
  }

  return true
}

const handleSubmit = async () => {
  if (!validateForm()) {
    return
  }

  submitting.value = true
  errorMessage.value = ''

  try {
    const response = await authApi.confirmPasswordReset({
      uid: route.params.uid,
      token: route.params.token,
      newPassword1: form.newPassword1,
      newPassword2: form.newPassword2
    })

    successMessage.value =
      response?.data?.message ||
      response?.message ||
      t('password.reset.successMessage')
    resetComplete.value = true
  } catch (error) {
    const responseData = error.response?.data
    errorMessage.value =
      responseData?.error ||
      responseData?.detail ||
      responseData?.message ||
      t('password.reset.unknownError')
  } finally {
    submitting.value = false
  }
}
</script>
