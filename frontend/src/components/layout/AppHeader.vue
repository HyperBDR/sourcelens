<template>
  <header
    class="z-30 flex-shrink-0 border-b border-line bg-surface/95 shadow-sm backdrop-blur"
  >
    <div class="px-4 sm:px-6 lg:px-8">
      <div class="flex justify-between items-center h-16">
        <div class="flex items-center gap-3">
          <button
            v-if="showMenuButton"
            @click="$emit('toggle-menu')"
            class="lg:hidden rounded-md p-2 text-ink-600 hover:bg-line-soft hover:text-ink-900 focus:outline-none focus:ring-2 focus:ring-primary-500"
          >
            <svg
              class="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </button>
          <h1 class="text-lg font-semibold text-ink-900 lg:hidden">
            {{ pageTitle }}
          </h1>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

defineProps({
  showMenuButton: {
    type: Boolean,
    default: true
  }
})

defineEmits(['toggle-menu'])

const { t } = useI18n()
const route = useRoute()

const pageTitle = computed(() => {
  const routeNames = {
    Dashboard: t('dashboard.title'),
    ResetPassword: t('password.reset.title')
  }
  return routeNames[route.name] || t('common.appName')
})
</script>
