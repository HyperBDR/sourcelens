<template>
  <div class="space-y-4">
    <div
      v-for="field in fields"
      :key="field.key"
      class="space-y-1"
    >
      <label
        :for="fieldId(field)"
        class="block text-sm font-medium text-ink-700"
      >
        {{ field.title || field.key }}
        <span v-if="isRequired(field)" class="text-danger-600">*</span>
      </label>

      <textarea
        v-if="isArrayField(field)"
        :id="fieldId(field)"
        :value="arrayValue(field).join('\n')"
        class="form-input min-h-24 font-mono"
        :placeholder="field.description || ''"
        :required="isRequired(field)"
        @input="updateArray(field, $event.target.value)"
      />
      <BaseSelect
        v-else-if="isResourceField(field)"
        :id="fieldId(field)"
        :model-value="fieldValue(field)"
        :required="isRequired(field)"
        @update:model-value="setField(field, $event)"
      >
        <option value="">{{ placeholder(field) }}</option>
        <option
          v-for="option in optionsFor(field)"
          :key="optionValue(option)"
          :value="optionValue(option)"
        >
          {{ optionLabel(option) }}
        </option>
      </BaseSelect>
      <input
        v-else-if="field.type === 'boolean'"
        :id="fieldId(field)"
        class="h-4 w-4 rounded border-line text-brand-600 focus:ring-brand-500"
        type="checkbox"
        :checked="Boolean(fieldValue(field))"
        @change="setField(field, $event.target.checked)"
      />
      <input
        v-else
        :id="fieldId(field)"
        class="form-input"
        :type="inputType(field)"
        :value="fieldValue(field)"
        :min="field.minimum"
        :max="field.maximum"
        :step="field.type === 'integer' ? 1 : undefined"
        :readonly="isReadOnly(field)"
        :required="isRequired(field)"
        :autocomplete="field.format === 'password' ? 'new-password' : undefined"
        :placeholder="field.description || ''"
        @input="setField(field, normalizeInput(field, $event.target.value))"
      />
      <p v-if="field.description" class="text-xs leading-5 text-ink-500">
        {{ field.description }}
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

import BaseSelect from '@/components/ui/BaseSelect.vue'

const props = defineProps({
  schema: { type: Object, default: () => ({}) },
  modelValue: { type: Object, default: () => ({}) },
  resources: { type: Object, default: () => ({}) }
})

const emit = defineEmits(['update:modelValue'])

const fields = computed(() => {
  const properties = props.schema?.properties
  if (!properties || typeof properties !== 'object') return []
  return Object.entries(properties)
    .map(([key, value]) => ({ key, ...(value || {}) }))
    .filter((field) => ['string', 'array', 'boolean', 'integer'].includes(field.type))
})

function fieldId(field) {
  return `manifest-field-${field.key}`
}

function isRequired(field) {
  return Array.isArray(props.schema?.required) && props.schema.required.includes(field.key)
}

function fieldValue(field) {
  return props.modelValue?.[field.key] ?? field.default ?? defaultValue(field)
}

function defaultValue(field) {
  if (field.type === 'boolean') return false
  if (field.type === 'array') return []
  return ''
}

function arrayValue(field) {
  const value = fieldValue(field)
  return Array.isArray(value) ? value : String(value || '').split(/[\n,]+/).map((item) => item.trim()).filter(Boolean)
}

function isArrayField(field) {
  return field.type === 'array'
}

function isResourceOptionField(field) {
  return field.format === 'provider-resource-option' && optionsFor(field).length > 0
}

function isResourceField(field) {
  return (
    (field.format === 'provider-resource' || isResourceOptionField(field)) &&
    optionsFor(field).length > 0
  )
}

function optionsFor(field) {
  const options =
    field.format === 'provider-resource-option'
      ? dependentOptions(field)
      : props.resources?.[field.resource]?.items
  const normalized = Array.isArray(options) ? [...options] : []
  const currentValue = fieldValue(field)
  if (
    currentValue !== '' &&
    !normalized.some((option) => optionValue(option) === currentValue)
  ) {
    normalized.push({ value: currentValue, label: currentValue })
  }
  return normalized
}

function dependentOptions(field) {
  const dependency = fields.value.find(
    (candidate) => candidate.key === field.depends_on
  )
  if (!dependency) return []
  const items = props.resources?.[dependency.resource]?.items
  if (!Array.isArray(items)) return []
  const selectedValue = fieldValue(dependency)
  const item = items.find(
    (candidate) => optionValue(candidate) === selectedValue
  )
  const options = item?.options?.[field.resource]
  return Array.isArray(options) ? options : []
}

function optionValue(option) {
  return typeof option === 'object' ? option.value ?? '' : option
}

function optionLabel(option) {
  return typeof option === 'object' ? option.label ?? option.value ?? '' : option
}

function placeholder(field) {
  return field.placeholder || 'Select an option'
}

function inputType(field) {
  if (field.format === 'password') return 'password'
  if (field.type === 'integer') return 'number'
  if (field.format === 'uri') return 'url'
  return 'text'
}

function isReadOnly(field) {
  return field.readOnly === true || field.readonly === true
}

function normalizeInput(field, value) {
  if (field.type === 'integer') {
    const number = Number(value)
    return Number.isFinite(number) ? number : ''
  }
  return value
}

function setField(field, value) {
  const nextValue = { ...props.modelValue, [field.key]: value }
  fields.value.forEach((candidate) => {
    if (candidate.depends_on === field.key) nextValue[candidate.key] = ''
  })
  emit('update:modelValue', nextValue)
}

function updateArray(field, value) {
  setField(
    field,
    String(value || '')
      .split(/[\n,]+/)
      .map((item) => item.trim())
      .filter(Boolean)
  )
}
</script>
