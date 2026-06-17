<template>
  <label class="flex items-center gap-2 text-sm text-ink-600">
    <input
      type="checkbox"
      :checked="modelValue"
      class="h-4 w-4 rounded border-line text-brand-600 focus:ring-brand-500"
      @change="$emit('update:modelValue', $event.target.checked)"
    />
    <span>{{ t('lensAdmin.fields.enabled') }}</span>
  </label>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

defineProps({
  modelValue: {
    type: Boolean,
    default: true
  }
})
defineEmits(['update:modelValue'])

const { t } = useI18n()
</script>
