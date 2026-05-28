<template>
  <div>
    <!-- Basic Information Card -->
    <div class="bg-white rounded border border-gray-200 shadow-sm">
      <div class="px-4 py-3 border-b border-gray-200 bg-gray-50">
        <div class="flex items-center gap-2 text-gray-800">
          <svg
            class="w-4 h-4 flex-none"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
            />
          </svg>
          <h3 class="text-sm font-semibold">
            {{ t('settings.basicInfo') }}
          </h3>
        </div>
      </div>
      <div class="p-4 space-y-3">
        <!-- Authentication Method -->
        <div>
          <h4 class="text-xs font-medium text-gray-900 mb-1.5">
            {{ t('settings.authMethod') }}
          </h4>
          <p class="text-sm text-gray-600 mb-3">
            <span
              v-if="authInfo && authInfo.method === 'email'"
              class="inline-flex items-center"
            >
              <svg
                class="h-4 w-4 mr-1.5 text-blue-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                />
              </svg>
              {{ t('settings.emailAuth') }}
            </span>
            <span
              v-else-if="authInfo && authInfo.method === 'oauth'"
              class="inline-flex items-center"
            >
              <svg
                class="h-4 w-4 mr-1.5 text-green-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                />
              </svg>
              {{ t('settings.oauthAuth') }}
            </span>
            <span v-else class="inline-flex items-center">
              <svg
                class="h-4 w-4 mr-1.5 text-blue-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                />
              </svg>
              {{ t('settings.emailAuth') }}
            </span>
          </p>
        </div>

        <!-- Security Email -->
        <div v-if="authInfo && authInfo.method === 'email'">
          <h4 class="text-sm font-medium text-gray-900 mb-2">
            {{ t('settings.securityEmail') }}
          </h4>
          <div class="flex items-center gap-2 mb-1">
            <svg
              class="w-4 h-4 text-gray-600"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
              />
            </svg>
            <span class="text-sm text-gray-700">{{
              userStore.userInfo?.email || ''
            }}</span>
          </div>
          <div class="text-xs text-gray-500 ml-6">
            {{ t('settings.securityEmailDesc') }}
          </div>
        </div>

        <!-- OAuth Users -->
        <div v-else-if="authInfo && authInfo.method === 'oauth'" class="mt-2">
          <div class="bg-green-50 rounded-lg p-3">
            <div class="flex items-center gap-2 mb-1">
              <svg
                class="w-4 h-4 text-green-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                />
              </svg>
              <span class="text-xs font-medium text-green-800">{{
                authInfo.provider || 'OAuth'
              }}</span>
            </div>
            <div class="text-sm text-green-900">
              {{ authInfo.login_identifier || '' }}
            </div>
          </div>
        </div>

        <!-- OAuth specific info -->
        <div
          v-if="authInfo?.method === 'oauth' && authInfo?.provider_email"
          class="bg-gray-50 rounded-lg p-3"
        >
          <div class="text-xs text-gray-500 space-y-1">
            <p>
              <span class="font-medium"
                >{{ t('settings.oauthProvider') }}:</span
              >
              {{ authInfo.provider }}
            </p>
            <p v-if="authInfo.provider_email">
              <span class="font-medium">{{ t('settings.oauthEmail') }}:</span>
              {{ authInfo.provider_email }}
            </p>
          </div>
        </div>

        <!-- Password Reset Button -->
        <div v-if="authInfo?.can_change_password" class="flex justify-end mt-4">
          <BaseButton
            variant="primary"
            class="w-full sm:w-auto"
            @click="showPasswordResetConfirm = true"
          >
            {{ t('settings.resetPassword') }}
          </BaseButton>
        </div>

        <!-- Password Change Info -->
        <div
          v-if="!authInfo?.can_change_password"
          class="bg-yellow-50 border border-yellow-200 rounded-lg p-3"
        >
          <div class="flex">
            <div class="flex-shrink-0">
              <svg
                class="h-5 w-5 text-yellow-400"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path
                  fill-rule="evenodd"
                  d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
                  clip-rule="evenodd"
                />
              </svg>
            </div>
            <div class="ml-3">
              <p class="text-sm text-yellow-700">
                {{ t('settings.oauthPasswordChangeInfo') }}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Password Reset Success/Error Messages -->
    <div v-if="resetEmailSent || resetEmailError" class="mb-6 mt-4">
      <!-- Password Reset Success Message -->
      <div v-if="resetEmailSent" class="rounded-md bg-green-50 p-4 mb-4">
        <div class="flex">
          <div class="flex-shrink-0">
            <svg
              class="h-5 w-5 text-green-400"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fill-rule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
                clip-rule="evenodd"
              />
            </svg>
          </div>
          <div class="ml-3">
            <p class="text-sm font-medium text-green-800">
              {{ t('settings.passwordResetEmailSent') }}
            </p>
            <p class="text-xs text-green-700 mt-1">
              {{ t('settings.passwordResetEmailSentDesc') }}
            </p>
          </div>
        </div>
      </div>

      <!-- Password Reset Error Message -->
      <div v-if="resetEmailError" class="rounded-md bg-red-50 p-4 mb-4">
        <div class="flex">
          <div class="flex-shrink-0">
            <svg
              class="h-5 w-5 text-red-400"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fill-rule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                clip-rule="evenodd"
              />
            </svg>
          </div>
          <div class="ml-3">
            <p class="text-sm font-medium text-red-800">
              {{ resetEmailError }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <!-- Password Reset Confirmation Modal -->
    <div
      v-if="showPasswordResetConfirm"
      class="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50"
      @click.self="showPasswordResetConfirm = false"
    >
      <div
        class="relative top-20 mx-auto p-6 border max-w-sm w-full shadow-lg rounded-md bg-white"
      >
        <div class="mt-3">
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-medium text-gray-900">
              {{ t('settings.confirmPasswordReset') }}
            </h3>
            <button
              @click="showPasswordResetConfirm = false"
              class="text-gray-400 hover:text-gray-600"
            >
              <svg
                class="w-6 h-6"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>

          <div class="mb-6">
            <div class="flex items-start gap-3">
              <div class="flex-shrink-0">
                <svg
                  class="h-6 w-6 text-blue-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                  />
                </svg>
              </div>
              <div>
                <p class="text-sm text-gray-700 mb-2">
                  {{ t('settings.passwordResetConfirmDesc') }}
                </p>
                <div class="bg-gray-50 rounded-lg p-3">
                  <div class="text-sm font-medium text-gray-900 mb-1">
                    {{ t('settings.securityEmail') }}
                  </div>
                  <div class="text-sm text-gray-700">
                    {{ userStore.userInfo?.email || '' }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="flex justify-end space-x-3">
            <BaseButton
              variant="secondary"
              @click="showPasswordResetConfirm = false"
            >
              {{ t('common.cancel') }}
            </BaseButton>
            <BaseButton
              variant="primary"
              :loading="sendingResetEmail"
              :disabled="sendingResetEmail"
              @click="confirmPasswordReset"
            >
              {{ t('settings.sendPasswordReset') }}
            </BaseButton>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/store/user'
import { authApi } from '@/api/auth'
import BaseButton from '@/components/ui/BaseButton.vue'

const { t } = useI18n()
const userStore = useUserStore()

const authInfo = computed(() => userStore.userInfo?.auth_info || null)

const sendingResetEmail = ref(false)
const resetEmailSent = ref(false)
const resetEmailError = ref('')
const showPasswordResetConfirm = ref(false)

const confirmPasswordReset = async () => {
  sendingResetEmail.value = true
  resetEmailError.value = ''
  resetEmailSent.value = false

  try {
    await authApi.resetPassword(userStore.userInfo?.email)
    resetEmailSent.value = true
    showPasswordResetConfirm.value = false

    // Show success message for 5 seconds
    setTimeout(() => {
      resetEmailSent.value = false
    }, 5000)
  } catch (error) {
    console.error('Password reset email failed:', error)

    // Handle different error response formats
    const responseData = error.response?.data
    if (responseData?.data?.error) {
      resetEmailError.value = responseData.data.error
    } else if (
      responseData?.data?.success === false &&
      responseData?.data?.error
    ) {
      resetEmailError.value = responseData.data.error
    } else if (responseData?.error) {
      resetEmailError.value = responseData.error
    } else if (responseData?.errors) {
      const errors = responseData.errors
      resetEmailError.value = Object.values(errors).flat().join(', ')
    } else if (responseData?.detail) {
      resetEmailError.value = responseData.detail
    } else if (responseData?.message) {
      resetEmailError.value = responseData.message
    } else {
      resetEmailError.value = t('settings.passwordResetError')
    }
  } finally {
    sendingResetEmail.value = false
  }
}
</script>
