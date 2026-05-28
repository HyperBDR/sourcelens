<template>
  <span
    :class="getStatusClass(status)"
    class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold whitespace-nowrap border shadow-sm"
  >
    <!-- Success icon -->
    <svg
      v-if="status === 'success'"
      class="w-3.5 h-3.5 flex-shrink-0"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M5 13l4 4L19 7"
      />
    </svg>
    <!-- Failed icon -->
    <svg
      v-else-if="status === 'failed'"
      class="w-3.5 h-3.5 flex-shrink-0"
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
    <!-- Processing icon (spinning) -->
    <svg
      v-else-if="status === 'processing'"
      class="animate-spin w-3.5 h-3.5 flex-shrink-0"
      fill="none"
      viewBox="0 0 24 24"
    >
      <circle
        class="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        stroke-width="4"
      ></circle>
      <path
        class="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
      ></path>
    </svg>
    <!-- Completed icon (checkmark) -->
    <svg
      v-else-if="status === 'completed'"
      class="w-3.5 h-3.5 flex-shrink-0"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M5 13l4 4L19 7"
      />
    </svg>
    <!-- Pending icon (clock) -->
    <svg
      v-else-if="status === 'pending'"
      class="w-3.5 h-3.5 flex-shrink-0"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
    <!-- Fetched icon (clock) -->
    <svg
      v-else-if="status === 'fetched'"
      class="w-3.5 h-3.5 flex-shrink-0"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
    <!-- Enabled icon -->
    <svg
      v-else-if="status === 'enabled'"
      class="w-3.5 h-3.5 flex-shrink-0"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
    <!-- Disabled icon -->
    <svg
      v-else-if="status === 'disabled'"
      class="w-3.5 h-3.5 flex-shrink-0"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"
      />
    </svg>
    <!-- Unknown status icon -->
    <svg
      v-else
      class="w-3.5 h-3.5 flex-shrink-0"
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="2"
        d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
    {{ getStatusText(status) }}
  </span>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  status: {
    type: String,
    default: 'unknown'
  }
})

const getStatusClass = (status) => {
  const classes = {
    success: 'bg-green-100 text-green-800 border-green-200',
    failed: 'bg-red-100 text-red-800 border-red-200',
    processing: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    fetched: 'bg-blue-100 text-blue-800 border-blue-200',
    pending: 'bg-yellow-100 text-yellow-800 border-yellow-200',
    completed: 'bg-green-100 text-green-800 border-green-200',
    enabled: 'bg-green-100 text-green-800 border-green-200',
    disabled: 'bg-gray-100 text-gray-700 border-gray-200'
  }
  return classes[status] || 'bg-gray-100 text-gray-700 border-gray-200'
}

const getStatusText = (status) => {
  const statusTexts = {
    success: t('common.status.success'),
    failed: t('common.status.failed'),
    processing: t('common.status.processing'),
    fetched: t('common.status.fetched'),
    pending: t('common.status.pending'),
    completed: t('common.status.completed'),
    enabled: t('common.status.enabled'),
    disabled: t('common.status.disabled')
  }
  return statusTexts[status] || status || t('common.status.unknown')
}
</script>
