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
      <div v-if="show" class="fixed inset-0 z-50 flex justify-end">
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
            class="relative z-10 flex h-full w-full flex-col bg-surface shadow-xl"
            :class="widthClass"
            @click.stop
          >
            <div class="flex flex-shrink-0 items-center justify-between border-b border-line px-6 py-4">
              <div class="min-w-0 flex-1">
                <h2 class="truncate text-base font-semibold text-ink-900">{{ title }}</h2>
                <p v-if="subtitle" class="mt-0.5 truncate text-sm text-ink-500">{{ subtitle }}</p>
              </div>
              <button
                type="button"
                class="ml-4 flex-shrink-0 rounded-md p-1.5 text-ink-400 transition-colors hover:bg-surface-sunken hover:text-ink-600 focus:outline-none"
                @click="$emit('close')"
              >
                <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
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
import { computed } from 'vue'

const props = defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  width: { type: String, default: '2xl' },
  closeOnBackdrop: { type: Boolean, default: true }
})

const emit = defineEmits(['close'])

const widthClass = computed(() => {
  const map = { sm: 'max-w-sm', md: 'max-w-md', lg: 'max-w-lg', xl: 'max-w-xl', '2xl': 'max-w-2xl' }
  return map[props.width] ?? 'max-w-2xl'
})

function handleBackdropClick() {
  if (props.closeOnBackdrop) emit('close')
}
</script>
