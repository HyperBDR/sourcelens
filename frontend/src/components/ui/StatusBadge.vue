<template>
  <span
    :class="getStatusClass(status)"
    class="inline-flex items-center gap-1.5 whitespace-nowrap text-sm font-medium"
  >
    <span :class="dotClass" class="h-1.5 w-1.5 shrink-0 rounded-full" />
    {{ getStatusText(status) }}
  </span>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  status: {
    type: String,
    default: 'unknown'
  }
})

const dotClass = computed(() => {
  const classes = {
    success: 'bg-success-600',
    failed: 'bg-danger-600',
    processing: 'bg-warning-600',
    running: 'bg-warning-600',
    fetched: 'bg-primary-600',
    pending: 'bg-warning-600',
    completed: 'bg-success-600',
    enabled: 'bg-success-600',
    disabled: 'bg-ink-400',
    cancelled: 'bg-ink-400'
  }
  return classes[props.status] || 'bg-ink-400'
})

const getStatusClass = (status) => {
  const classes = {
    success: 'text-success-700',
    failed: 'text-danger-700',
    processing: 'text-warning-700',
    running: 'text-warning-700',
    fetched: 'text-primary-700',
    pending: 'text-warning-700',
    completed: 'text-success-700',
    enabled: 'text-success-700',
    disabled: 'text-ink-500',
    cancelled: 'text-ink-500'
  }
  return classes[status] || 'text-ink-500'
}

const getStatusText = (status) => {
  const statusTexts = {
    success: t('common.status.success'),
    failed: t('common.status.failed'),
    processing: t('common.status.processing'),
    running: t('common.status.processing'),
    fetched: t('common.status.fetched'),
    pending: t('common.status.pending'),
    completed: t('common.status.completed'),
    enabled: t('common.status.enabled'),
    disabled: t('common.status.disabled'),
    cancelled: t('common.status.disabled')
  }
  return statusTexts[status] || status || t('common.status.unknown')
}
</script>
