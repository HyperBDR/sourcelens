<template>
  <button
    v-if="isAnonymous"
    type="button"
    class="anon-login-btn"
    :class="{ 'anon-login-btn-collapsed': collapsed && !isMobile }"
    :title="t('auth.signIn')"
    @click="$emit('require-login')"
  >
    <LogIn :size="18" :stroke-width="2" aria-hidden="true" />
    <span v-if="!collapsed || isMobile">{{ t('auth.signIn') }}</span>
  </button>

  <div v-else ref="dockMenuRef" class="dock-menu-wrap">
    <button
      class="dock-trigger"
      :class="[
        dockMenuOpen ? 'dock-trigger-open' : '',
        collapsed ? 'dock-trigger-collapsed' : ''
      ]"
      type="button"
      @click="dockMenuOpen = !dockMenuOpen"
    >
      <div class="dock-avatar" :class="avatarBgColor">
        <span>{{ userInitials }}</span>
      </div>
      <div v-if="!collapsed || isMobile" class="min-w-0 flex-1 text-left">
        <div class="truncate text-sm font-medium text-ink-900">
          {{ displayName }}
        </div>
        <div class="truncate text-xs text-ink-500">
          {{ t('platforms.workspace') }}
        </div>
      </div>
      <svg
        v-if="!collapsed || isMobile"
        class="h-4 w-4 shrink-0 text-ink-500 transition-transform"
        :class="{ 'rotate-180': dockMenuOpen }"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        aria-hidden="true"
      >
        <path d="m6 9 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <Transition
      enter-active-class="transition ease-out duration-100"
      enter-from-class="transform opacity-0 translate-y-1 scale-95"
      enter-to-class="transform opacity-100 translate-y-0 scale-100"
      leave-active-class="transition ease-in duration-75"
      leave-from-class="transform opacity-100 translate-y-0 scale-100"
      leave-to-class="transform opacity-0 translate-y-1 scale-95"
    >
      <div v-if="dockMenuOpen" class="dock-menu">
        <div v-if="isAdmin" class="dock-section">
          <router-link
            to="/management/users"
            class="dock-link"
            @click="dockMenuOpen = false"
          >
            <Shield :size="18" :stroke-width="2" aria-hidden="true" />
            <span class="truncate">{{ t('platforms.adminConsole') }}</span>
          </router-link>
        </div>

        <div
          class="dock-section"
          :class="{ 'border-t border-line': isAdmin }"
        >
          <button type="button" class="dock-link" @click="openMyShares">
            <Share2 :size="18" :stroke-width="2" aria-hidden="true" />
            <span class="truncate">{{ t('lens.qa.mineEntry') }}</span>
          </button>
          <button type="button" class="dock-link" @click="openSettings">
            <Settings :size="18" :stroke-width="2" aria-hidden="true" />
            <span class="truncate">{{ t('common.settings') }}</span>
          </button>
          <button type="button" class="dock-link" @click="handleLogout">
            <LogOut :size="18" :stroke-width="2" aria-hidden="true" />
            <span class="truncate">{{ t('common.logout') }}</span>
          </button>
          <div class="dock-build-info">{{ buildInfo }}</div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { onClickOutside } from '@vueuse/core'
import { LogIn, LogOut, Settings, Share2, Shield } from '@lucide/vue'

import { useUserStore } from '@/store/user'
import { useUiStore } from '@/store/ui'

defineProps({
  collapsed: { type: Boolean, default: false },
  isMobile: { type: Boolean, default: false }
})
const emit = defineEmits(['require-login', 'open-my-shares'])

const { t } = useI18n()
const router = useRouter()
const userStore = useUserStore()
const uiStore = useUiStore()

const dockMenuOpen = ref(false)
const dockMenuRef = ref(null)
const buildInfo = [
  import.meta.env.VITE_APP_VERSION || 'dev',
  import.meta.env.VITE_APP_RELEASE_DATE
]
  .filter(Boolean)
  .join(' · ')
onClickOutside(dockMenuRef, () => {
  dockMenuOpen.value = false
})

const isAnonymous = computed(() => !userStore.isAuthenticated)
const isAdmin = computed(() => userStore.userHasFeature('admin_console'))

const displayName = computed(() => {
  const userInfo = userStore.userInfo
  if (!userInfo) return 'User'
  if (userInfo.display_name) return userInfo.display_name
  if (userInfo.first_name && userInfo.last_name) {
    return `${userInfo.first_name} ${userInfo.last_name}`
  }
  return userInfo.username || userInfo.email || 'User'
})

const userInitials = computed(() => {
  const name = displayName.value.trim()
  return name.charAt(0).toUpperCase() || 'U'
})

const avatarBgColor = computed(() => {
  const colors = [
    'bg-blue-500',
    'bg-indigo-500',
    'bg-emerald-500',
    'bg-rose-500',
    'bg-amber-500',
    'bg-cyan-500'
  ]
  const charCode = userInitials.value.charCodeAt(0)
  return colors[charCode % colors.length]
})

function openMyShares() {
  emit('open-my-shares')
  dockMenuOpen.value = false
}

function openSettings() {
  uiStore.openSettings()
  dockMenuOpen.value = false
}

async function handleLogout() {
  try {
    await userStore.logout()
  } catch {
    // Fall through to local redirect.
  } finally {
    dockMenuOpen.value = false
    await router.push('/login')
  }
}
</script>

<style scoped>
.dock-menu-wrap {
  @apply relative;
}

.dock-trigger {
  @apply flex w-full items-center gap-3 rounded-xl border border-line bg-surface px-3 py-2 text-left shadow-sm transition-colors;
}

.dock-trigger:hover,
.dock-trigger-open {
  @apply border-primary-200 bg-primary-50;
}

.dock-trigger-collapsed {
  @apply justify-center px-0;
}

.anon-login-btn {
  @apply flex w-full items-center justify-center gap-2 rounded-xl border border-primary-200 bg-primary-50 px-3 py-2.5 text-sm font-medium text-primary-700 shadow-sm transition-colors;
}

.anon-login-btn:hover {
  @apply border-primary-300 bg-primary-100;
}

.anon-login-btn-collapsed {
  @apply gap-0 px-0;
}

.dock-avatar {
  @apply flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white;
}

.dock-menu {
  @apply absolute bottom-full left-0 z-40 mb-2 w-full overflow-visible rounded-2xl border border-line bg-surface shadow-xl;
}

.dock-section {
  @apply border-b border-line px-3 py-3 last:border-b-0;
}

.dock-link {
  @apply flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-ink-700 transition-colors;
}

.dock-link:hover {
  @apply bg-line-soft text-ink-900;
}

.dock-build-info {
  @apply px-3 pb-1 pt-2 text-left text-xs text-ink-400;
}
</style>
