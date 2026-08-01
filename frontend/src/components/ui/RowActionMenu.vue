<template>
  <div
    class="row-action-menu inline-flex"
    :class="{ 'row-action-menu-open': open }"
  >
    <button
      ref="triggerRef"
      type="button"
      class="row-action-trigger inline-flex h-11 w-11 items-center justify-center rounded-lg border border-transparent text-ink-500 transition-colors hover:border-line hover:bg-line-soft hover:text-ink-900 focus:outline-none focus:ring-2 focus:ring-primary-500/20 md:h-8 md:w-8"
      :aria-label="label || t('common.moreActions')"
      aria-haspopup="menu"
      :aria-expanded="open"
      @click="toggleMenu"
      @keydown.down.prevent="openMenu(true)"
    >
      <MoreVertical :size="18" :stroke-width="2" aria-hidden="true" />
    </button>

    <Teleport to="body">
      <template v-if="open">
        <div
          class="fixed inset-0 z-40"
          @click="closeMenu({ restoreFocus: true })"
        />
        <div
          ref="menuRef"
          role="menu"
          class="fixed z-50 max-h-[calc(100vh-1rem)] min-w-44 overflow-y-auto rounded-lg border border-line bg-surface py-1 shadow-lg"
          :style="menuStyle"
          @keydown="handleMenuKeydown"
        >
          <template v-for="action in actions" :key="action.key">
            <div v-if="action.divider" class="my-1 border-t border-line" />
            <button
              type="button"
              role="menuitem"
              class="flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary-500/20 disabled:cursor-not-allowed disabled:opacity-50 md:min-h-0"
              :class="[
                action.variant === 'danger'
                  ? 'text-danger-600 hover:bg-danger-50'
                  : 'text-ink-700 hover:bg-line-soft',
                action.disabled ? 'cursor-not-allowed opacity-50' : ''
              ]"
              :disabled="action.loading"
              :aria-disabled="action.disabled || undefined"
              :aria-label="actionAriaLabel(action)"
              :title="action.disabledReason || action.label"
              @click="selectAction(action)"
            >
              <span class="inline-flex h-4 w-4 items-center justify-center">
                <span
                  v-if="action.loading"
                  class="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-r-transparent"
                />
                <component
                  :is="action.icon"
                  v-else-if="action.icon"
                  :size="16"
                  :stroke-width="2"
                  aria-hidden="true"
                />
              </span>
              <span>{{ action.label }}</span>
            </button>
          </template>
        </div>
      </template>
    </Teleport>
  </div>
</template>

<script setup>
import { MoreVertical } from '@lucide/vue'
import { nextTick, onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  actions: {
    type: Array,
    required: true
  },
  label: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['select'])

const { t } = useI18n()
const menuRef = ref(null)
const menuStyle = ref({})
const open = ref(false)
const triggerRef = ref(null)

function closeMenu({ restoreFocus = false } = {}) {
  open.value = false
  window.removeEventListener('scroll', closeMenu, true)
  window.removeEventListener('resize', closeMenu)
  if (restoreFocus) nextTick(() => triggerRef.value?.focus())
}

function focusAction(index = 0) {
  nextTick(() => {
    const items = [
      ...(menuRef.value?.querySelectorAll('[role="menuitem"]') || [])
    ].filter((item) => !item.disabled)
    items[index]?.focus()
  })
}

function openMenu(focusFirst = false) {
  const rect = triggerRef.value?.getBoundingClientRect()
  if (!rect) return

  const menuWidth = 176
  const estimatedItemHeight = window.innerWidth < 768 ? 44 : 40
  const estimatedHeight = props.actions.reduce((height, action) => {
    const dividerHeight = action.divider ? 9 : 0
    return height + estimatedItemHeight + dividerHeight
  }, 8)
  const opensUpward = rect.bottom + estimatedHeight > window.innerHeight
  menuStyle.value = {
    left: `${Math.max(8, Math.min(rect.right - menuWidth, window.innerWidth - menuWidth - 8))}px`,
    top: opensUpward ? undefined : `${rect.bottom + 4}px`,
    bottom: opensUpward ? `${window.innerHeight - rect.top + 4}px` : undefined
  }
  open.value = true
  window.addEventListener('scroll', closeMenu, true)
  window.addEventListener('resize', closeMenu)
  if (focusFirst) focusAction()
}

function toggleMenu() {
  if (open.value) {
    closeMenu()
    return
  }
  openMenu(true)
}

function selectAction(action) {
  if (action.disabled || action.loading) return
  closeMenu({ restoreFocus: true })
  emit('select', action.key)
}

function actionAriaLabel(action) {
  if (action.disabled && action.disabledReason) {
    return `${action.label}. ${action.disabledReason}`
  }
  return action.label
}

function handleMenuKeydown(event) {
  const items = [...menuRef.value.querySelectorAll('[role="menuitem"]')].filter(
    (item) => !item.disabled
  )
  const currentIndex = items.indexOf(document.activeElement)

  if (event.key === 'Escape') {
    event.preventDefault()
    closeMenu({ restoreFocus: true })
  } else if (event.key === 'ArrowDown') {
    event.preventDefault()
    items[(currentIndex + 1) % items.length]?.focus()
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    items[(currentIndex - 1 + items.length) % items.length]?.focus()
  } else if (event.key === 'Home') {
    event.preventDefault()
    items[0]?.focus()
  } else if (event.key === 'End') {
    event.preventDefault()
    items.at(-1)?.focus()
  }
}

onBeforeUnmount(() => closeMenu())
</script>
