<template>
  <label
    class="relative inline-flex w-full items-center md:w-auto"
    :class="[rootHeightClass, rootWidthClass]"
  >
    <input
      type="date"
      :value="modelValue"
      :min="min"
      :max="max"
      :disabled="disabled"
      :lang="toDocumentLang(locale)"
      :aria-label="ariaLabel || resolvedPlaceholder"
      :class="[
        'base-date-input relative z-0 w-full rounded-md border border-gray-300',
        'bg-white px-2.5 pr-10 text-sm focus:outline-none focus:ring-1',
        'focus:ring-primary-500 disabled:cursor-not-allowed disabled:opacity-60',
        rootHeightClass,
        modelValue ? 'text-gray-900' : 'text-transparent is-empty',
        inputClass
      ]"
      @change="onChange"
    />
    <span
      v-if="!modelValue"
      class="pointer-events-none absolute inset-y-0 left-2.5 right-10 z-10 flex items-center overflow-hidden text-sm leading-none whitespace-nowrap text-gray-400"
    >
      {{ resolvedPlaceholder }}
    </span>
    <svg
      class="pointer-events-none absolute top-1/2 right-2.5 z-[2] h-4 w-4 -translate-y-1/2 text-gray-500"
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden="true"
    >
      <path
        fill-rule="evenodd"
        d="M5.75 2a.75.75 0 0 1 .75.75V4h7V2.75a.75.75 0 0 1 1.5 0V4h.25A2.75 2.75 0 0 1 18 6.75v8.5A2.75 2.75 0 0 1 15.25 18H4.75A2.75 2.75 0 0 1 2 15.25v-8.5A2.75 2.75 0 0 1 4.75 4H5V2.75A.75.75 0 0 1 5.75 2Zm-1 5.5c-.69 0-1.25.56-1.25 1.25v6.5c0 .69.56 1.25 1.25 1.25h10.5c.69 0 1.25-.56 1.25-1.25v-6.5c0-.69-.56-1.25-1.25-1.25H4.75Z"
        clip-rule="evenodd"
      />
    </svg>
  </label>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import { toDocumentLang } from '@/utils/documentLang'

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  min: {
    type: String,
    default: undefined
  },
  max: {
    type: String,
    default: undefined
  },
  disabled: {
    type: Boolean,
    default: false
  },
  placeholder: {
    type: String,
    default: ''
  },
  ariaLabel: {
    type: String,
    default: ''
  },
  inputClass: {
    type: String,
    default: ''
  },
  mobileTouch: {
    type: Boolean,
    default: true
  },
  compact: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

const { t, locale } = useI18n()

const resolvedPlaceholder = computed(
  () => props.placeholder || t('common.datePlaceholder')
)

const rootHeightClass = computed(() =>
  props.mobileTouch ? 'h-11 md:h-9' : 'h-9'
)

const rootWidthClass = computed(() => (props.compact ? 'md:w-36' : ''))

const onChange = (event) => {
  emit('update:modelValue', event.target.value)
  emit('change', event)
}
</script>

<style scoped>
.base-date-input.is-empty {
  color: transparent;
}

.base-date-input::-webkit-calendar-picker-indicator {
  opacity: 0;
}
</style>
