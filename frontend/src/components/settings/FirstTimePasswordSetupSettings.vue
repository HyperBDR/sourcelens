<template>
  <div class="space-y-5">
    <p class="text-sm text-gray-500">
      {{ t('passwordManagement.setup.description') }}
    </p>

    <div class="rounded-lg border border-line bg-gray-50 p-4">
      <p class="text-sm text-gray-700">
        {{
          t('passwordManagement.setup.emailNotice', {
            email: userStore.userInfo?.email || '—'
          })
        }}
      </p>
    </div>

    <BaseButton
      v-if="!codeSent"
      type="button"
      variant="primary"
      :loading="sendingCode"
      :disabled="sendingCode"
      @click="sendCode"
    >
      {{
        sendingCode
          ? t('passwordManagement.setup.sendingCode')
          : t('passwordManagement.setup.sendCode')
      }}
    </BaseButton>

    <form v-else class="space-y-4" novalidate @submit.prevent="handleSubmit">
      <BaseInput
        v-model="form.code"
        :label="t('passwordManagement.setup.code')"
        :placeholder="t('passwordManagement.setup.codePlaceholder')"
        type="text"
        autocomplete="one-time-code"
        :error="errors.code"
        :disabled="settingPassword"
        required
      />
      <BaseInput
        v-model="form.newPassword"
        :label="t('passwordManagement.setup.newPassword')"
        type="password"
        autocomplete="new-password"
        :error="errors.newPassword"
        :disabled="settingPassword"
        required
      />
      <BaseInput
        v-model="form.confirmPassword"
        :label="t('passwordManagement.setup.confirmPassword')"
        type="password"
        autocomplete="new-password"
        :error="errors.confirmPassword"
        :disabled="settingPassword"
        required
      />

      <div class="flex flex-wrap items-center gap-4">
        <BaseButton
          type="submit"
          variant="primary"
          :loading="settingPassword"
          :disabled="settingPassword || sendingCode"
        >
          {{
            settingPassword
              ? t('passwordManagement.setup.setting')
              : t('passwordManagement.setup.submit')
          }}
        </BaseButton>
        <button
          type="button"
          class="text-sm text-primary-600 hover:underline disabled:opacity-50"
          :disabled="settingPassword || sendingCode"
          @click="sendCode"
        >
          {{ t('passwordManagement.setup.resend') }}
        </button>
      </div>
    </form>

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
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { authApi } from '@/api/auth'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import { passwordManagementMessages } from '@/locales/passwordManagement'
import { useUserStore } from '@/store/user'
import {
  getApiErrorData,
  getFirstApiError,
  getPasswordPolicyError,
  getPasswordSetupErrorKey
} from '@/utils/password'

const emit = defineEmits(['completed'])
const { t } = useI18n({
  useScope: 'local',
  messages: passwordManagementMessages
})
const userStore = useUserStore()
const form = reactive({ code: '', newPassword: '', confirmPassword: '' })
const errors = reactive({ code: '', newPassword: '', confirmPassword: '' })
const codeSent = ref(false)
const sendingCode = ref(false)
const settingPassword = ref(false)
const success = ref(false)
const statusMessage = ref('')

const refreshUser = async () => {
  const response = await authApi.getProfile()
  userStore.setUser(response.data.data || response.data)
}

const showApiError = async (error) => {
  const data = getApiErrorData(error)
  const errorKey = getPasswordSetupErrorKey(data.error_code)
  if (errorKey === 'alreadySet') {
    await refreshUser()
    emit('completed')
  }
  statusMessage.value =
    getFirstApiError(error) || t(`passwordManagement.setup.${errorKey}`)
}

const sendCode = async () => {
  sendingCode.value = true
  success.value = false
  statusMessage.value = ''
  try {
    await authApi.sendPasswordSetupCode()
    codeSent.value = true
    success.value = true
    statusMessage.value = t('passwordManagement.setup.codeSent')
  } catch (error) {
    await showApiError(error)
  } finally {
    sendingCode.value = false
  }
}

const validateForm = () => {
  errors.code = ''
  errors.newPassword = ''
  errors.confirmPassword = ''
  statusMessage.value = ''

  if (!/^\d{6}$/.test(form.code)) {
    errors.code = t('passwordManagement.setup.codeRequired')
  }
  if (!form.newPassword) {
    errors.newPassword = t('passwordManagement.setup.newRequired')
  }
  if (!form.confirmPassword) {
    errors.confirmPassword = t('passwordManagement.setup.confirmRequired')
  }
  if (errors.code || errors.newPassword || errors.confirmPassword) return false
  if (form.newPassword !== form.confirmPassword) {
    errors.confirmPassword = t('passwordManagement.setup.mismatch')
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

  settingPassword.value = true
  success.value = false
  try {
    await authApi.setupPassword({
      code: form.code,
      newPassword1: form.newPassword,
      newPassword2: form.confirmPassword
    })
    success.value = true
    statusMessage.value = t('passwordManagement.setup.success')
    emit('completed')
    await refreshUser()
  } catch (error) {
    await showApiError(error)
  } finally {
    settingPassword.value = false
  }
}
</script>
