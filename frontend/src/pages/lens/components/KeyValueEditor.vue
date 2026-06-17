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
      <input
        :value="row.value"
        :placeholder="valueLabel"
        class="rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
        @input="updateRow(index, 'value', $event.target.value)"
      />
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
  }
})
const emit = defineEmits(['update:modelValue'])

const { t } = useI18n()

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
