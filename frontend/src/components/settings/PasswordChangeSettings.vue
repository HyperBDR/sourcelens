<template>
  <div v-if="!canChangePassword" class="space-y-5">
    <p class="text-sm text-gray-500">
      {{ t('passwordManagement.security.unavailable') }}
    </p>
  </div>

  <div v-else class="space-y-5">
    <p class="text-sm text-gray-500">
      {{ t('passwordManagement.security.description') }}
    </p>

    <form class="space-y-4" novalidate @submit.prevent="handleSubmit">
      <BaseInput
        v-model="form.currentPassword"
        :label="t('passwordManagement.security.currentPassword')"
        type="password"
        autocomplete="current-password"
        :error="errors.currentPassword"
        :disabled="loading"
        required
      />
      <BaseInput
        v-model="form.newPassword"
        :label="t('passwordManagement.security.newPassword')"
        type="password"
        autocomplete="new-password"
        :error="errors.newPassword"
        :disabled="loading"
        required
      />
      <BaseInput
        v-model="form.confirmPassword"
        :label="t('passwordManagement.security.confirmPassword')"
        type="password"
        autocomplete="new-password"
        :error="errors.confirmPassword"
        :disabled="loading"
        required
      />

      <div
        v-if="statusMessage"
        class="rounded-lg border p-3 text-sm"
        :class="
          success
            ? 'border-green-200 bg-green-50 text-green-700'
            : 'border-danger-100 bg-danger-50 text-danger-700'
        "
        :role="success ? 'status' : 'alert'"
      >
        {{ statusMessage }}
      </div>

      <div>
        <BaseButton
          type="submit"
          variant="primary"
          :loading="loading"
          :disabled="loading"
        >
          {{
            loading
              ? t('passwordManagement.security.changing')
              : t('passwordManagement.security.submit')
          }}
        </BaseButton>
      </div>
    </form>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { authApi } from '@/api/auth'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import { passwordManagementMessages } from '@/locales/passwordManagement'
import { useUserStore } from '@/store/user'
import {
  getApiErrorData,
  getFirstApiError,
  getPasswordPolicyError
} from '@/utils/password'

const { t } = useI18n({
  useScope: 'local',
  messages: passwordManagementMessages
})
const userStore = useUserStore()
const canChangePassword = computed(
  () => userStore.userInfo?.auth_info?.can_change_password === true
)
const form = reactive({
  currentPassword: '',
  newPassword: '',
  confirmPassword: ''
})
const errors = reactive({
  currentPassword: '',
  newPassword: '',
  confirmPassword: ''
})
const loading = ref(false)
const success = ref(false)
const statusMessage = ref('')

const validateForm = () => {
  errors.currentPassword = ''
  errors.newPassword = ''
  errors.confirmPassword = ''
  statusMessage.value = ''

  if (!form.currentPassword) {
    errors.currentPassword = t('passwordManagement.security.currentRequired')
  }
  if (!form.newPassword) {
    errors.newPassword = t('passwordManagement.security.newRequired')
  }
  if (!form.confirmPassword) {
    errors.confirmPassword = t('passwordManagement.security.confirmRequired')
  }
  if (errors.currentPassword || errors.newPassword || errors.confirmPassword) {
    return false
  }
  if (form.newPassword !== form.confirmPassword) {
    errors.confirmPassword = t('passwordManagement.security.mismatch')
    return false
  }

  const policyError = getPasswordPolicyError(form.newPassword)
  if (policyError) {
    errors.newPassword = t(`passwordManagement.policy.${policyError}`)
    return false
  }
  return true
}

const handleSubmit = async () => {
  if (!validateForm()) return

  loading.value = true
  success.value = false
  try {
    await authApi.changePassword({
      oldPassword: form.currentPassword,
      newPassword1: form.newPassword,
      newPassword2: form.confirmPassword
    })
    form.currentPassword = ''
    form.newPassword = ''
    form.confirmPassword = ''
    success.value = true
    statusMessage.value = t('passwordManagement.security.success')
  } catch (error) {
    const data = getApiErrorData(error)
    const fieldErrors = data.errors || data
    const oldPasswordError =
      fieldErrors.oldPassword ||
      fieldErrors.old_password ||
      fieldErrors.old_password_error
    if (oldPasswordError) {
      errors.currentPassword = t('passwordManagement.security.wrongCurrent')
    } else {
      statusMessage.value =
        getFirstApiError(error) || t('passwordManagement.security.error')
    }
  } finally {
    loading.value = false
  }
}
</script>
