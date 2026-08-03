<template>
  <div :class="rootClasses">
    <label
      v-if="label"
      :for="selectId"
      class="block text-sm font-medium text-ink-800"
    >
      {{ label }}
      <span v-if="required" class="text-danger-600">*</span>
    </label>

    <div class="relative">
      <select
        v-model="selectedValue"
        v-bind="selectAttrs"
        :disabled="disabled"
        :required="required"
        :class="selectClasses"
        @change="handleChange"
        @focus="$emit('focus', $event)"
        @blur="$emit('blur', $event)"
      >
        <slot />
      </select>

      <svg
        aria-hidden="true"
        :class="[
          'pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2',
          disabled ? 'text-ink-300' : 'text-ink-500'
        ]"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          d="m8 10 4 4 4-4"
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
        />
      </svg>
    </div>

    <p v-if="error" :id="errorId" class="text-sm text-danger-700">
      {{ error }}
    </p>

    <p v-else-if="help" :id="helpId" class="text-sm text-ink-500">
      {{ help }}
    </p>
  </div>
</template>

<script setup>
import { computed, ref, useAttrs } from 'vue'

import { applyModelModifiers } from './baseSelect'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  modelValue: {
    default: ''
  },
  modelModifiers: {
    type: Object,
    default: () => ({})
  },
  label: {
    type: String,
    default: ''
  },
  help: {
    type: String,
    default: ''
  },
  error: {
    type: String,
    default: ''
  },
  invalid: {
    type: Boolean,
    default: false
  },
  required: {
    type: Boolean,
    default: false
  },
  disabled: {
    type: Boolean,
    default: false
  },
  size: {
    type: String,
    default: 'md',
    validator: (value) => ['sm', 'md', 'lg'].includes(value)
  },
  variant: {
    type: String,
    default: 'default',
    validator: (value) => ['default', 'unstyled'].includes(value)
  },
  fullWidth: {
    type: Boolean,
    default: true
  },
  mobileTouch: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'change', 'focus', 'blur'])
const attrs = useAttrs()
const generatedId = ref(`select-${Math.random().toString(36).substring(2, 11)}`)

const selectId = computed(() => attrs.id || generatedId.value)
const errorId = computed(() => `${selectId.value}-error`)
const helpId = computed(() => `${selectId.value}-help`)
const isInvalid = computed(() => props.invalid || Boolean(props.error))
const describedBy = computed(() => {
  let feedbackId = ''
  if (props.error) feedbackId = errorId.value
  else if (props.help) feedbackId = helpId.value

  return (
    [attrs['aria-describedby'], feedbackId].filter(Boolean).join(' ') ||
    undefined
  )
})

const selectAttrs = computed(() => {
  const forwardedAttrs = { ...attrs }
  delete forwardedAttrs.class
  delete forwardedAttrs.id
  delete forwardedAttrs['aria-describedby']
  delete forwardedAttrs['aria-invalid']

  return {
    ...forwardedAttrs,
    id: selectId.value,
    'aria-describedby': describedBy.value,
    'aria-invalid': isInvalid.value ? 'true' : attrs['aria-invalid']
  }
})

const rootClasses = computed(() => [
  'space-y-1',
  props.fullWidth ? 'w-full' : 'inline-block',
  attrs.class
])

const selectedValue = computed({
  get: () => props.modelValue,
  set: (value) => {
    emit('update:modelValue', applyModelModifiers(value, props.modelModifiers))
  }
})

const selectClasses = computed(() => {
  const sizeClasses = {
    sm: 'px-2 py-1 pr-8 text-xs',
    md: 'px-3 py-2 pr-10 text-sm',
    lg: 'px-4 py-3 pr-12 text-base'
  }
  const variantClasses = {
    default:
      'rounded-lg border bg-surface text-ink-900 shadow-sm transition-colors hover:border-ink-300 focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 disabled:bg-surface-sunken disabled:text-ink-400 disabled:opacity-50',
    unstyled:
      'border-0 bg-transparent text-ink-900 shadow-none focus:outline-none focus:ring-0 disabled:text-ink-400 disabled:opacity-50'
  }
  const invalidClasses = isInvalid.value
    ? 'border-danger-600 focus:border-danger-600 focus:ring-danger-600/20'
    : 'border-line'
  const spacingClasses =
    props.variant === 'unstyled'
      ? 'py-0 pl-0 pr-8 text-sm'
      : sizeClasses[props.size]

  return [
    'block w-full appearance-none disabled:cursor-not-allowed',
    spacingClasses,
    variantClasses[props.variant],
    props.variant === 'default' ? invalidClasses : '',
    props.mobileTouch ? 'min-h-11 md:min-h-0' : ''
  ]
    .filter(Boolean)
    .join(' ')
})

function handleChange(event) {
  emit('change', event)
}
</script>
