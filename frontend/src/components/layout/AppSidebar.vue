<template>
  <!-- Mobile overlay -->
  <Transition
    enter-active-class="transition-opacity duration-200"
    enter-from-class="opacity-0"
    enter-to-class="opacity-100"
    leave-active-class="transition-opacity duration-150"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
  >
    <div
      v-if="showMobileMenu && isMobile"
      @click="$emit('close')"
      class="fixed inset-0 bg-gray-900 bg-opacity-50 z-40 lg:hidden"
    />
  </Transition>

  <!-- Sidebar -->
  <aside
    :class="[
      'bg-white border-r border-gray-200 flex flex-col transition-transform duration-300 ease-in-out w-64 flex-shrink-0 h-full',
      isMobile ? 'fixed inset-y-0 left-0 z-50' : 'static',
      isMobile && !showMobileMenu ? '-translate-x-full' : 'translate-x-0'
    ]"
  >
    <!-- Logo and close button -->
    <div
      class="flex items-center justify-between h-16 px-4 border-b border-gray-200"
    >
      <router-link
        :to="homePath"
        class="flex items-center space-x-2 flex-1"
        @click="isMobile && $emit('close')"
      >
        <img
          src="/android-chrome-192x192.png"
          alt="SourceLens Logo"
          class="w-8 h-8"
        />
        <span class="text-xl font-semibold text-gray-900">{{
          t('common.appName')
        }}</span>
      </router-link>
      <button
        v-if="isMobile"
        @click="$emit('close')"
        class="p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100"
      >
        <svg
          class="w-5 h-5"
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

    <!-- Navigation -->
    <nav class="flex-1 px-3 py-4 space-y-1 overflow-y-auto flex flex-col">
      <div class="flex-1 space-y-1">
        <router-link
          v-if="userStore.userHasFeature('workspace')"
          to="/dashboard"
          class="nav-item"
          :class="isActive('/dashboard') ? 'nav-item-active' : ''"
          @click="isMobile && $emit('close')"
          @mouseenter="preloadRoute('/dashboard')"
        >
          <svg
            class="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
            />
          </svg>
          <span>{{ t('dashboard.title') }}</span>
        </router-link>

      </div>

      <!-- Settings Menu -->
      <div class="mt-auto pt-4 border-t border-gray-200">
        <router-link
          :to="{ name: 'SettingsProfile' }"
          class="nav-item"
          :class="isActive('/settings/profile') ? 'nav-item-active' : ''"
          @mouseenter="preloadRoute('/settings/profile')"
        >
          <svg
            class="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
            />
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
            />
          </svg>
          <span>{{ t('common.settings') }}</span>
        </router-link>
      </div>
    </nav>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/store/user'

const props = defineProps({
  showMobileMenu: {
    type: Boolean,
    default: false
  }
})

defineEmits(['close'])

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const homePath = computed(() => userStore.getUserLandingPath())

const MOBILE_BREAKPOINT = 1024

const isMobile = computed(() => {
  if (typeof window === 'undefined') return false
  return window.innerWidth < MOBILE_BREAKPOINT
})

const isActive = (path) => {
  if (path === '/dashboard') {
    return route.path === '/dashboard' || route.path === '/'
  }
  // For submenu items, use exact match or starts with
  return route.path === path || route.path.startsWith(path + '/')
}

// Preload route component on link hover for faster navigation
// Use a cache to avoid duplicate preloads
const preloadCache = new Set()

const preloadRoute = (path) => {
  // Skip if already preloaded
  if (preloadCache.has(path)) {
    return
  }

  try {
    const route = router.resolve(path)
    if (route.matched.length > 0) {
      const matched = route.matched[0]
      // Preload the component if it's lazy-loaded
      if (matched.components) {
        Object.values(matched.components).forEach((component) => {
          if (typeof component === 'function') {
            // Mark as preloading
            preloadCache.add(path)
            component().catch(() => {
              // Remove from cache on error so we can retry
              preloadCache.delete(path)
            })
          }
        })
      }
    }
  } catch (error) {
    // Ignore preload errors silently
  }
}

</script>

<style scoped>
.nav-item {
  @apply flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition-all duration-200;
}

.nav-item-active {
  @apply bg-primary-50 text-primary-600;
}

.nav-item-parent {
  @apply w-full cursor-pointer font-semibold text-gray-800;
}

.nav-item-parent:hover {
  @apply bg-gray-50;
}

.nav-item-child {
  @apply relative pl-10 py-2 text-sm font-normal text-gray-600;
  margin-left: 0.75rem;
  border-radius: 0.375rem;
}

.nav-item-child:hover {
  @apply bg-gray-50;
}

.nav-item-child.nav-item-active {
  @apply bg-primary-50 text-primary-600 font-medium;
}

.menu-group {
  @apply space-y-0 mb-1.5;
}

.submenu {
  @apply overflow-hidden pl-0 mt-1 space-y-0.5;
  transition: all 0.2s ease-in-out;
}

.submenu .nav-item {
  @apply ml-0;
}

/* Add a subtle left border indicator for child items */
.nav-item-child::before {
  content: '';
  @apply absolute left-6 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-gray-300 rounded;
  transition: all 0.2s;
}

.nav-item-child.nav-item-active::before {
  @apply bg-primary-500 w-1;
}

/* Improve icon spacing in parent items */
.nav-item-parent svg:first-child {
  @apply flex-shrink-0;
}

.nav-item-parent span {
  @apply flex-shrink-0;
}

.nav-item-parent svg:last-child {
  @apply flex-shrink-0 ml-1 opacity-70;
  transition:
    transform 0.2s ease-in-out,
    opacity 0.2s;
}

.nav-item-parent:hover svg:last-child {
  @apply opacity-100;
}
</style>
