<template>
  <div class="space-y-4">
    <div>
      <h2 class="text-lg font-semibold text-ink-900">
        {{ t('passwordManagement.forgot.title') }}
      </h2>
      <p class="mt-1 text-sm text-ink-500">
        {{ t('passwordManagement.forgot.description') }}
      </p>
    </div>

    <div
      v-if="sent"
      class="rounded-lg border border-green-200 bg-green-50 p-4 text-sm text-green-700"
      role="status"
    >
      {{ t('passwordManagement.forgot.success') }}
    </div>

    <form v-else class="space-y-4" novalidate @submit.prevent="handleSubmit">
      <BaseInput
        v-model="email"
        :label="t('passwordManagement.forgot.email')"
        type="email"
        autocomplete="email"
        :placeholder="t('passwordManagement.forgot.emailPlaceholder')"
        :error="emailError"
        :disabled="loading"
        required
      />

      <div
        v-if="requestError"
        class="rounded-lg border border-danger-100 bg-danger-50 p-4"
        role="alert"
      >
        <p class="text-sm text-danger-700">{{ requestError }}</p>
      </div>

      <BaseButton
        type="submit"
        variant="primary"
        class="w-full"
        :loading="loading"
        :disabled="loading"
      >
        {{
          loading
            ? t('passwordManagement.forgot.sending')
            : t('passwordManagement.forgot.submit')
        }}
      </BaseButton>
    </form>

    <button
      type="button"
      class="block w-full text-center text-sm text-ink-500 hover:underline"
      @click="$emit('back')"
    >
      {{ backLabel || t('passwordManagement.forgot.back') }}
    </button>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { authApi } from '@/api/auth'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import { passwordManagementMessages } from '@/locales/passwordManagement'

const props = defineProps({
  initialEmail: {
    type: String,
    default: ''
  },
  backLabel: {
    type: String,
    default: ''
  }
})
defineEmits(['back'])

const { t } = useI18n({
  useScope: 'local',
  messages: passwordManagementMessages
})
const email = ref(props.initialEmail)
const emailErrorKey = ref('')
const requestFailed = ref(false)
const loading = ref(false)
const sent = ref(false)
const emailError = computed(() =>
  emailErrorKey.value ? t(emailErrorKey.value) : ''
)
const requestError = computed(() =>
  requestFailed.value ? t('passwordManagement.forgot.error') : ''
)

const validateEmail = () => {
  emailErrorKey.value = ''
  const value = email.value.trim()
  if (!value) {
    emailErrorKey.value = 'passwordManagement.forgot.required'
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
    emailErrorKey.value = 'passwordManagement.forgot.invalid'
  }
  return !emailErrorKey.value
}

const handleSubmit = async () => {
  if (!validateEmail()) return

  loading.value = true
  requestFailed.value = false
  try {
    await authApi.resetPassword(email.value.trim())
    sent.value = true
  } catch (_error) {
    requestFailed.value = true
  } finally {
    loading.value = false
  }
}
</script>
