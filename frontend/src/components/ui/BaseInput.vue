<template>
  <div class="space-y-1">
    <label
      v-if="label"
      :for="inputId"
      class="block text-sm font-medium text-theme"
    >
      {{ label }}
      <span v-if="required" class="text-danger-600">*</span>
    </label>

    <div class="relative">
      <input
        :id="inputId"
        :name="name"
        :type="type"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :required="required"
        :autocomplete="autocomplete"
        :class="inputClasses"
        @input="$emit('update:modelValue', $event.target.value)"
        @blur="$emit('blur', $event)"
        @focus="$emit('focus', $event)"
      />

      <div
        v-if="$slots.icon"
        class="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none"
      >
        <slot name="icon" />
      </div>

      <div
        v-if="error && showValidationIcon"
        class="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none"
      >
        <svg
          class="w-5 h-5 text-danger-600"
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path
            fill-rule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
            clip-rule="evenodd"
          />
        </svg>
      </div>

      <div
        v-else-if="valid && !error"
        class="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none"
      >
        <svg
          class="w-5 h-5 text-success"
          fill="currentColor"
          viewBox="0 0 20 20"
        >
          <path
            fill-rule="evenodd"
            d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"
            clip-rule="evenodd"
          />
        </svg>
      </div>

      <div
        v-else-if="$slots.rightIcon"
        class="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none"
      >
        <slot name="rightIcon" />
      </div>
    </div>

    <p v-if="error" class="text-sm text-danger-700">
      {{ error }}
    </p>

    <p v-else-if="help" class="text-sm text-theme-muted">
      {{ help }}
    </p>
  </div>
</template>

<script setup>
import { computed, ref, useSlots } from 'vue'

const props = defineProps({
  modelValue: {
    type: [String, Number],
    default: ''
  },
  type: {
    type: String,
    default: 'text'
  },
  name: {
    type: String,
    default: ''
  },
  label: {
    type: String,
    default: ''
  },
  placeholder: {
    type: String,
    default: ''
  },
  autocomplete: {
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
  valid: {
    type: Boolean,
    default: false
  },
  showValidationIcon: {
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
  }
})

defineEmits(['update:modelValue', 'blur', 'focus'])

const slots = useSlots()
const inputId = ref(`input-${Math.random().toString(36).substr(2, 9)}`)

const inputClasses = computed(() => {
  const baseClasses =
    'block w-full rounded-lg border bg-surface px-3 py-2 text-sm text-theme shadow-sm placeholder:text-theme-subtle focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-500/20 disabled:cursor-not-allowed disabled:opacity-50'
  const errorClass = props.error
    ? 'border-danger-300 focus:border-danger-500 focus:ring-danger-500/20'
    : 'border-line'
  const sizeClasses = {
    sm: 'px-2 py-1 text-xs',
    md: 'px-3 py-2 text-sm',
    lg: 'px-4 py-3 text-base'
  }
  const iconPadding = slots.icon ? 'pl-10' : ''
  const hasRightIcon =
    (props.valid && !props.error) ||
    (props.error && props.showValidationIcon) ||
    slots.rightIcon
  const rightIconPadding = hasRightIcon ? 'pr-10' : ''

  return [
    baseClasses,
    errorClass,
    sizeClasses[props.size],
    iconPadding,
    rightIconPadding
  ]
    .filter(Boolean)
    .join(' ')
})
</script>
