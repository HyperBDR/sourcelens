<template>
  <div class="space-y-2">
    <div
      v-for="(row, index) in modelValue"
      :key="index"
      class="grid grid-cols-1 gap-2 rounded-md border border-line bg-surface-sunken p-2 md:grid-cols-[1fr_1fr_auto]"
    >
      <input
        :value="row.key"
        :placeholder="keyLabel"
        class="rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
        @input="updateRow(index, 'key', $event.target.value)"
      />
      <div class="min-w-0">
        <div
          v-if="isMaskedSensitiveRow(row)"
          class="mb-1 text-right text-[11px] font-medium text-success-700"
        >
          {{ configuredLabel }}
        </div>
        <input
          :value="row.value"
          :type="isSensitiveRow(row) ? 'password' : 'text'"
          :autocomplete="isSensitiveRow(row) ? 'new-password' : 'off'"
          :placeholder="valueLabel"
          class="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
          @input="updateRow(index, 'value', $event.target.value)"
        />
      </div>
      <BaseButton size="sm" variant="outline" @click="removeRow(index)">
        {{ t('lensAdmin.actions.removeRow') }}
      </BaseButton>
    </div>
    <BaseButton size="sm" variant="outline" @click="addRow">
      {{ t('lensAdmin.actions.addRow') }}
    </BaseButton>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

import BaseButton from '@/components/ui/BaseButton.vue'

import { isSensitiveMcpConfigKey, MCP_CONFIG_MASK } from '../mcpConfig'

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  },
  keyLabel: {
    type: String,
    required: true
  },
  valueLabel: {
    type: String,
    required: true
  },
  maskSensitiveValues: {
    type: Boolean,
    default: false
  },
  configuredLabel: {
    type: String,
    default: ''
  }
})
const emit = defineEmits(['update:modelValue'])

const { t } = useI18n()

function isSensitiveRow(row) {
  return props.maskSensitiveValues && isSensitiveMcpConfigKey(row.key)
}

function isMaskedSensitiveRow(row) {
  return (
    isSensitiveRow(row) &&
    row.value === MCP_CONFIG_MASK &&
    props.configuredLabel
  )
}

function updateRow(index, field, value) {
  const rows = props.modelValue.map((item) => ({ ...item }))
  rows[index] = { ...rows[index], [field]: value }
  emit('update:modelValue', rows)
}

function removeRow(index) {
  emit(
    'update:modelValue',
    props.modelValue.filter((_, rowIndex) => rowIndex !== index)
  )
}

function addRow() {
  emit('update:modelValue', [...props.modelValue, { key: '', value: '' }])
}
</script>
