<template>
  <Teleport to="body">
    <div
      class="pointer-events-none fixed right-4 left-4 top-20 z-[9998] flex max-h-[calc(100vh-6rem)] flex-col gap-2 overflow-y-auto sm:top-4 sm:left-auto sm:w-96"
      aria-live="polite"
    >
      <TransitionGroup
        enter-active-class="transition duration-200 ease-out motion-reduce:transition-none"
        enter-from-class="translate-x-4 opacity-0"
        enter-to-class="translate-x-0 opacity-100"
        leave-active-class="transition duration-150 ease-in motion-reduce:transition-none"
        leave-from-class="translate-x-0 opacity-100"
        leave-to-class="translate-x-4 opacity-0"
      >
        <button
          v-for="notification in state.notifications"
          :key="notification.id"
          type="button"
          class="pointer-events-auto flex w-full items-center gap-3 rounded-xl border bg-surface p-3 text-left shadow-lg transition-colors hover:bg-surface-hover"
          :class="notificationClass(notification.type)"
          @click="openNotification(notification)"
        >
          <BrandLogo
            variant="mark"
            altText=""
            wrapperClass="shrink-0 gap-0 [&_img]:h-9 [&_img]:w-9"
          />
          <span class="min-w-0 flex-1">
            <span
              v-if="notification.title"
              class="block truncate text-sm font-semibold text-theme"
            >
              {{ notification.title }}
            </span>
            <span
              class="block truncate text-sm leading-5"
              :class="messageClass(notification.type)"
            >
              {{ notification.message }}
            </span>
          </span>
        </button>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { useRouter } from 'vue-router'

import BrandLogo from '@/components/layout/BrandLogo.vue'
import { useSessionActivity } from '@/composables/useSessionActivity'

const router = useRouter()
const { dismissNotification, state } = useSessionActivity()

function notificationClass(type) {
  return type === 'error' ? 'border-red-200' : 'border-line'
}

function messageClass(type) {
  return type === 'error' ? 'text-red-700' : 'text-theme-secondary'
}

function openNotification(notification) {
  dismissNotification(notification.id)
  if (notification.to) {
    void router.push(notification.to)
  }
}
</script>
