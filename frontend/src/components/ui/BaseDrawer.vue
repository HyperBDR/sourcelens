<template>
  <Teleport to="body">
    <Transition
      enter-active-class="transition-opacity duration-200 ease-out"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition-opacity duration-150 ease-in"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="show"
        ref="dialogRef"
        class="fixed inset-0 z-[60] flex justify-end"
        role="dialog"
        aria-modal="true"
        :aria-label="title"
      >
        <div class="fixed inset-0 bg-black/40" @click="handleBackdropClick" />
        <Transition
          enter-active-class="transition-transform duration-300 ease-out"
          enter-from-class="translate-x-full"
          enter-to-class="translate-x-0"
          leave-active-class="transition-transform duration-200 ease-in"
          leave-from-class="translate-x-0"
          leave-to-class="translate-x-full"
        >
          <div
            v-if="show"
            tabindex="-1"
            class="relative z-10 flex h-full w-full flex-col bg-surface shadow-xl"
            :class="widthClass"
            @click.stop
          >
            <div
              class="flex flex-shrink-0 items-center justify-between border-b border-line px-6 py-4"
            >
              <div class="min-w-0 flex-1">
                <h2 class="truncate text-base font-semibold text-ink-900">
                  {{ title }}
                </h2>
                <p v-if="subtitle" class="mt-0.5 truncate text-sm text-ink-500">
                  {{ subtitle }}
                </p>
              </div>
              <div
                v-if="$slots.actions"
                class="flex flex-shrink-0 items-center gap-2"
              >
                <slot name="actions" />
              </div>
              <button
                type="button"
                class="ml-3 flex-shrink-0 rounded-md p-1.5 text-ink-400 transition-colors hover:bg-surface-sunken hover:text-ink-600 focus:outline-none"
                :aria-label="t('common.close')"
                @click="requestClose"
              >
                <svg
                  class="h-5 w-5"
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
              </button>
            </div>
            <div v-if="$slots.tabs" class="flex-shrink-0 bg-surface">
              <slot name="tabs" />
            </div>
            <div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
              <slot />
            </div>
            <div
              v-if="$slots.footer"
              class="flex-shrink-0 border-t border-line bg-surface-sunken px-6 py-4"
            >
              <slot name="footer" />
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  acquireBodyScrollLock,
  isTopDialog,
  registerDialog,
  unregisterDialog,
  releaseBodyScrollLock
} from './dialogScrollLock'

const { t } = useI18n()

const props = defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  width: { type: String, default: '2xl' },
  closeOnBackdrop: { type: Boolean, default: true }
})

const emit = defineEmits(['close'])
const dialogRef = ref(null)

const focusableSelector = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])'
].join(',')

let previousFocus = null
let dialogActive = false
const dialogToken = Symbol('base-drawer')

const widthClass = computed(() => {
  const map = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-xl',
    '2xl': 'max-w-2xl'
  }
  return map[props.width] ?? 'max-w-2xl'
})

function handleBackdropClick() {
  if (props.closeOnBackdrop) requestClose()
}

function handleKeydown(event) {
  if (!props.show || !isTopDialog(dialogToken)) return
  if (event.key === 'Escape') {
    event.preventDefault()
    requestClose()
    return
  }
  if (event.key !== 'Tab') return

  const focusable = getFocusableElements()
  if (focusable.length === 0) {
    event.preventDefault()
    dialogRef.value?.focus()
    return
  }
  const first = focusable[0]
  const last = focusable[focusable.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

function requestClose() {
  emit('close')
}

function getFocusableElements() {
  if (!dialogRef.value) return []
  return [...dialogRef.value.querySelectorAll(focusableSelector)].filter(
    (element) => element.getClientRects().length > 0
  )
}

function activateDialog() {
  if (dialogActive) return
  dialogActive = true
  previousFocus = document.activeElement
  acquireBodyScrollLock()
  registerDialog(dialogToken)
  window.addEventListener('keydown', handleKeydown)
  nextTick(() => {
    const initialFocus = getFocusableElements().find((element) =>
      element.matches('input, select, textarea, [autofocus]')
    )
    ;(initialFocus || getFocusableElements()[0] || dialogRef.value)?.focus()
  })
}

function deactivateDialog() {
  if (!dialogActive) return
  dialogActive = false
  window.removeEventListener('keydown', handleKeydown)
  unregisterDialog(dialogToken)
  releaseBodyScrollLock()
  const focusTarget = previousFocus
  previousFocus = null
  nextTick(() => {
    if (focusTarget?.isConnected) focusTarget.focus()
  })
}

watch(
  () => props.show,
  (show) => {
    if (typeof window === 'undefined') return
    if (show) {
      activateDialog()
    } else {
      deactivateDialog()
    }
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  if (typeof window !== 'undefined') {
    deactivateDialog()
  }
})
</script>
