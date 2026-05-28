<template>
  <header
    class="bg-white shadow-sm border-b border-gray-200 flex-shrink-0 z-30"
  >
    <div class="px-4 sm:px-6 lg:px-8">
      <div class="flex justify-between items-center h-16">
        <!-- Mobile menu button -->
        <div class="flex items-center gap-3">
          <button
            v-if="showMenuButton"
            @click="$emit('toggle-menu')"
            class="lg:hidden p-2 rounded-md text-gray-600 hover:text-gray-900 hover:bg-gray-100 focus:outline-none focus:ring-2 focus:ring-primary-500"
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
          <!-- Page title (optional, can be dynamic based on route) -->
          <h1 class="text-lg font-semibold text-gray-900 lg:hidden">
            {{ pageTitle }}
          </h1>
        </div>

        <!-- User menu -->
        <div class="flex items-center space-x-4">
          <LanguageSwitcher />
          <PlatformSwitcher />
          <div class="relative" ref="userMenuRef">
            <button
              @click="toggleUserMenu"
              class="flex items-center space-x-2 text-sm text-gray-700 hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-primary-500 rounded-lg px-2 py-1"
            >
              <div
                :class="avatarBgColor"
                class="w-8 h-8 rounded-full flex items-center justify-center"
              >
                <span class="text-white font-medium text-sm">
                  {{ userInitials }}
                </span>
              </div>
              <span class="hidden sm:block">{{ displayName }}</span>
              <svg
                class="w-4 h-4 transition-transform"
                :class="{ 'rotate-180': showUserMenu }"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </button>

            <!-- Dropdown menu -->
            <Transition
              enter-active-class="transition ease-out duration-100"
              enter-from-class="transform opacity-0 scale-95"
              enter-to-class="transform opacity-100 scale-100"
              leave-active-class="transition ease-in duration-75"
              leave-from-class="transform opacity-100 scale-100"
              leave-to-class="transform opacity-0 scale-95"
            >
              <div
                v-if="showUserMenu"
                class="absolute right-0 mt-2 w-80 bg-white rounded-md shadow-lg py-2 z-50 border border-gray-200"
              >
                <!-- User Info -->
                <div class="px-4 py-2 border-b border-gray-100">
                  <div class="font-semibold text-gray-900 truncate">
                    {{ displayName }}
                  </div>
                </div>

                <!-- AI Email Card (Always at the top) -->
                <div v-if="userStore.userInfo?.virtual_email" class="px-4 py-2">
                  <div
                    class="bg-gradient-to-r from-primary-50 to-blue-50 rounded-lg p-3 border border-primary-100"
                  >
                    <div class="flex items-center gap-2 mb-2">
                      <svg
                        class="w-4 h-4 text-primary-600"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          stroke-width="2"
                          d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                        />
                      </svg>
                      <span class="text-xs text-primary-700 font-semibold">{{
                        t('virtualEmail.yourAddress')
                      }}</span>
                    </div>
                    <div class="flex items-center gap-2">
                      <div class="flex-1 min-w-0">
                        <div
                          class="text-primary-900 text-sm font-medium truncate"
                          :title="userStore.userInfo?.virtual_email"
                        >
                          {{ userStore.userInfo?.virtual_email }}
                        </div>
                      </div>
                      <button
                        @click.stop="copyVirtualEmail"
                        class="flex-shrink-0 p-1.5 text-primary-600 hover:text-primary-700 hover:bg-primary-100 rounded-md transition-all"
                        :title="t('settings.copyEmail')"
                      >
                        <svg
                          v-if="!copied"
                          class="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            stroke-linecap="round"
                            stroke-linejoin="round"
                            stroke-width="2"
                            d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
                          />
                        </svg>
                        <svg
                          v-else
                          class="w-4 h-4 text-green-600"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            stroke-linecap="round"
                            stroke-linejoin="round"
                            stroke-width="2"
                            d="M5 13l4 4L19 7"
                          />
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>

                <!-- User Settings Button -->
                <div class="px-4 py-2">
                  <router-link
                    :to="settingsRoute"
                    class="flex items-center gap-2 text-sm text-gray-700 hover:text-gray-900 hover:bg-gray-50 rounded-md px-2 py-1.5 transition-colors"
                    @click="showUserMenu = false"
                  >
                    <svg
                      class="w-4 h-4 text-gray-400"
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

                <!-- Divider -->
                <div class="border-t border-gray-100 my-1"></div>

                <!-- Logout Button -->
                <button
                  @click="handleLogout"
                  class="block w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-100"
                >
                  {{ t('common.logout') }}
                </button>
              </div>
            </Transition>
          </div>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/store/user'
import LanguageSwitcher from '@/components/ui/LanguageSwitcher.vue'
import PlatformSwitcher from '@/components/layout/PlatformSwitcher.vue'

defineProps({
  showMenuButton: {
    type: Boolean,
    default: true
  }
})

defineEmits(['toggle-menu'])

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const showUserMenu = ref(false)
const userMenuRef = ref(null)
const copied = ref(false)
const settingsRoute = computed(() => {
  return { name: 'SettingsProfile' }
})

const pageTitle = computed(() => {
  const routeNames = {
    Dashboard: t('dashboard.title'),
    ResetPassword: t('password.reset.title'),
    SettingsProfile: t('common.settings')
  }
  return routeNames[route.name] || t('common.appName')
})

const displayName = computed(() => {
  const userInfo = userStore.userInfo
  if (!userInfo) return 'User'

  // Prioritize display_name from backend (uses first_name + last_name for OAuth users)
  if (userInfo.display_name) {
    return userInfo.display_name
  }

  // Fallback to first_name + last_name if available
  if (userInfo.first_name && userInfo.last_name) {
    return `${userInfo.first_name} ${userInfo.last_name}`
  }

  // Fallback to first_name only
  if (userInfo.first_name) {
    return userInfo.first_name
  }

  // Final fallback to username
  return userInfo.username || 'User'
})

const userInitials = computed(() => {
  const name = displayName.value
  // Extract first character from display name (could be first name or full name)
  const firstChar = name.trim().charAt(0).toUpperCase()
  return firstChar || 'U'
})

const avatarBgColor = computed(() => {
  // Generate consistent background color based on user's first initial
  const initial = userInitials.value
  const colors = [
    'bg-blue-500',
    'bg-indigo-500',
    'bg-purple-500',
    'bg-pink-500',
    'bg-rose-500',
    'bg-red-500',
    'bg-orange-500',
    'bg-amber-500',
    'bg-yellow-500',
    'bg-lime-500',
    'bg-green-500',
    'bg-emerald-500',
    'bg-teal-500',
    'bg-cyan-500',
    'bg-sky-500'
  ]

  // Use character code to deterministically select a color
  const charCode = initial.charCodeAt(0)
  const colorIndex = charCode % colors.length
  return colors[colorIndex]
})

const toggleUserMenu = () => {
  showUserMenu.value = !showUserMenu.value
  if (!showUserMenu.value) {
    copied.value = false
  }
}

const copyVirtualEmail = async () => {
  try {
    const virtualEmail = userStore.userInfo?.virtual_email
    if (virtualEmail) {
      await navigator.clipboard.writeText(virtualEmail)
      copied.value = true
      setTimeout(() => {
        copied.value = false
      }, 2000)
    }
  } catch (error) {
    console.error('Failed to copy email:', error)
  }
}

const handleLogout = async () => {
  try {
    await userStore.logout()
  } catch (error) {
    console.error('Logout failed:', error)
  } finally {
    // Always close menu and redirect to login, even if logout API call failed
    showUserMenu.value = false
    router.push('/login')
  }
}

const handleClickOutside = (event) => {
  if (userMenuRef.value && !userMenuRef.value.contains(event.target)) {
    showUserMenu.value = false
    copied.value = false
  }
}

onMounted(async () => {
  document.addEventListener('click', handleClickOutside)

  // Refresh user info to ensure we have the latest data (including virtual_email)
  // This is important after OAuth setup completion
  if (userStore.user && !userStore.userInfo?.virtual_email) {
    await userStore.checkAuthStatus()
  }
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
.nav-link {
  @apply text-gray-500 hover:text-gray-700 px-3 py-2 rounded-md text-sm font-medium transition-colors;
}

.nav-link-active {
  @apply text-primary-600 bg-primary-50;
}
</style>
