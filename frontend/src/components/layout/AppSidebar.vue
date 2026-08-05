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
      class="fixed inset-0 z-40 bg-ink-950/50 lg:hidden"
    />
  </Transition>

  <!-- Sidebar -->
  <aside
    :class="[
      'app-sidebar flex h-full w-64 flex-shrink-0 flex-col border-r border-line bg-surface-sunken transition-transform duration-300 ease-in-out',
      isMobile ? 'fixed inset-y-0 left-0 z-50' : 'static',
      isMobile && !showMobileMenu ? '-translate-x-full' : 'translate-x-0'
    ]"
  >
    <!-- Logo and close button -->
    <div
      class="app-sidebar-header flex h-16 items-center justify-between border-b border-line px-4"
    >
      <router-link
        :to="homePath"
        class="flex flex-1 items-center justify-start"
        @click="isMobile && $emit('close')"
      >
        <BrandLogo
          variant="responsive"
          wrapperClass="origin-left scale-[0.62]"
        />
      </router-link>
      <button
        v-if="isMobile"
        @click="$emit('close')"
        class="rounded-md p-2 text-theme-muted hover:bg-line-soft hover:text-theme"
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
    <nav class="flex flex-1 flex-col space-y-1 overflow-y-auto px-3 py-4">
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

        <router-link
          v-if="userStore.userHasFeature('workspace')"
          to="/"
          class="nav-item"
          :class="isActive('/lens') ? 'nav-item-active' : ''"
          @click="isMobile && $emit('close')"
          @mouseenter="preloadRoute('/')"
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
              d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.79 9.79 0 01-4-.82L3 20l1.82-4.91A7.8 7.8 0 013 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
            />
          </svg>
          <span>Lens</span>
        </router-link>
      </div>
    </nav>

    <div class="border-t border-line p-3">
      <SidebarQuickMenu />
    </div>
  </aside>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/store/user'
import { useIsMobile } from '@/composables/useIsMobile'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import SidebarQuickMenu from '@/components/layout/SidebarQuickMenu.vue'

defineProps({
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

const { isMobile } = useIsMobile()

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
  @apply flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-theme-secondary transition-colors hover:bg-line-soft hover:text-theme;
}

.nav-item-active {
  @apply bg-brand-50 text-brand-700;
}

.nav-item-parent {
  @apply w-full cursor-pointer font-semibold text-theme;
}

.nav-item-parent:hover {
  @apply bg-line-soft;
}

.nav-item-child {
  @apply relative pl-10 py-2 text-sm font-normal text-theme-secondary;
  margin-left: 0.75rem;
  border-radius: 0.375rem;
}

.nav-item-child:hover {
  @apply bg-line-soft;
}

.nav-item-child.nav-item-active {
  @apply bg-brand-50 text-brand-700 font-medium;
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
  @apply absolute left-6 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded bg-line;
  transition: all 0.2s;
}

.nav-item-child.nav-item-active::before {
  @apply w-1 bg-brand-500;
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

:global(:root[data-theme='dark'] .app-sidebar) {
  border-right: 0;
}

:global(:root[data-theme='dark'] .app-sidebar-header) {
  border-bottom: 0;
}
</style>
