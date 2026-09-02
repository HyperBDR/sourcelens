<template>
  <div class="space-y-4">
    <div
      v-for="field in fields"
      :key="field.key"
      class="space-y-1"
    >
      <label
        :for="fieldId(field)"
        class="flex items-center justify-between gap-2 text-sm font-medium text-ink-700"
      >
        <span>
          {{ field.title || field.key }}
          <span v-if="isRequired(field)" class="text-danger-600">*</span>
        </span>
        <slot name="field-actions" :field="field" />
      </label>

      <div
        v-if="isTreeField(field) && shouldRenderTree(field)"
        class="max-h-64 overflow-y-auto rounded-lg border border-line bg-surface-sunken p-2"
      >
        <div
          v-for="group in treeGroups(field)"
          :key="group.owner"
          class="mb-2 overflow-hidden rounded-md border border-line bg-surface last:mb-0"
        >
          <label class="flex cursor-pointer items-center gap-2 bg-surface-sunken px-3 py-2 text-sm font-medium hover:bg-line-soft">
            <input
              type="checkbox"
              class="h-4 w-4 shrink-0 rounded-sm border-2 border-ink-300 accent-brand-600"
              :checked="groupSelected(field, group)"
              :indeterminate="groupPartial(field, group)"
              @change="toggleGroup(field, group, $event.target.checked)"
            />
            <span class="min-w-0 flex-1 truncate text-ink-800">{{ group.owner }}</span>
            <span class="text-xs font-normal text-ink-500">{{ group.items.length }}</span>
          </label>
          <div class="space-y-0.5 border-t border-line px-2 py-1.5">
            <label
              v-for="item in group.items"
              :key="optionValue(item)"
              class="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-surface-sunken"
            >
              <input
                type="checkbox"
                class="h-4 w-4 shrink-0 rounded-sm border-2 border-ink-300 accent-brand-600"
                :checked="arrayValue(field).includes(optionValue(item))"
                @change="toggleArrayItem(field, optionValue(item), $event.target.checked)"
              />
              <span class="min-w-0 truncate text-ink-700">{{ optionLabel(item) }}</span>
              <span v-if="item.metadata?.private" class="text-xs text-ink-500">Private</span>
            </label>
          </div>
        </div>
      </div>
      <textarea
        v-else-if="isArrayField(field) && !isTreeField(field)"
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
      <p
        v-if="field.description && (!isTreeField(field) || shouldRenderTree(field))"
        class="text-xs leading-5 text-ink-500"
      >
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

function isTreeField(field) {
  return isArrayField(field) && field.format === 'provider-resource'
}

function shouldRenderTree(field) {
  return optionsFor(field).length > 0
}

function treeGroups(field) {
  const groups = new Map()
  optionsFor(field).forEach((item) => {
    const value = optionValue(item)
    const owner = value.includes('/') ? value.split('/')[0] : 'Resources'
    if (!groups.has(owner)) groups.set(owner, [])
    groups.get(owner).push(item)
  })
  return [...groups.entries()].map(([owner, items]) => ({ owner, items }))
}

function groupSelected(field, group) {
  const selected = arrayValue(field)
  return group.items.every((item) => selected.includes(optionValue(item)))
}

function groupPartial(field, group) {
  const selected = arrayValue(field)
  const count = group.items.filter((item) => selected.includes(optionValue(item))).length
  return count > 0 && count < group.items.length
}

function toggleGroup(field, group, checked) {
  const selected = new Set(arrayValue(field))
  group.items.forEach((item) => {
    if (checked) selected.add(optionValue(item))
    else selected.delete(optionValue(item))
  })
  setField(field, [...selected])
}

function toggleArrayItem(field, value, checked) {
  const selected = new Set(arrayValue(field))
  if (checked) selected.add(value)
  else selected.delete(value)
  setField(field, [...selected])
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
  const currentValues = Array.isArray(currentValue)
    ? currentValue
    : [currentValue]
  currentValues.filter((value) => value !== '').forEach((value) => {
    if (!normalized.some((option) => optionValue(option) === value)) {
      normalized.push({ value, label: value })
    }
  })
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
