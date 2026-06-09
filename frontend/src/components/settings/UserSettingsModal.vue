<template>
  <Transition
    enter-active-class="transition duration-200 ease-out"
    enter-from-class="opacity-0"
    enter-to-class="opacity-100"
    leave-active-class="transition duration-150 ease-in"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
  >
    <div
      v-if="show"
      class="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6"
      @click.self="emit('close')"
    >
      <div class="absolute inset-0 bg-[#1c1916]/45 backdrop-blur-[2px]" />

      <Transition
        enter-active-class="transition duration-200 ease-out"
        enter-from-class="opacity-0 translate-y-3 scale-[0.98]"
        enter-to-class="opacity-100 translate-y-0 scale-100"
        leave-active-class="transition duration-150 ease-in"
        leave-from-class="opacity-100 translate-y-0 scale-100"
        leave-to-class="opacity-0 translate-y-3 scale-[0.98]"
      >
        <section
          v-if="show"
          class="relative flex max-h-[86vh] w-full max-w-4xl flex-col overflow-hidden rounded-3xl border border-line bg-surface shadow-[0_32px_120px_rgba(42,39,34,0.22)]"
        >
          <header
            class="flex items-start justify-between gap-4 border-b border-line px-5 py-4 sm:px-6"
          >
            <div class="min-w-0">
              <div class="text-[11px] font-semibold uppercase tracking-wide text-ink-500">
                {{ t('settings.modal.label') }}
              </div>
              <h2 class="mt-1 text-xl font-semibold text-ink-900">
                {{ t('settings.modal.title') }}
              </h2>
              <p class="mt-1 text-sm text-ink-500">
                {{ t('settings.modal.subtitle') }}
              </p>
            </div>

            <button
              type="button"
              class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-ink-500 transition-colors hover:bg-line-soft hover:text-ink-900"
              :aria-label="t('common.close')"
              @click="emit('close')"
            >
              <svg
                class="h-5 w-5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.25"
                aria-hidden="true"
              >
                <path
                  d="M6 18L18 6M6 6l12 12"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
          </header>

          <div class="min-h-0 flex-1 overflow-y-auto">
            <div class="px-5 py-5 sm:px-6">
              <section class="space-y-4">
                <div class="rounded-2xl border border-line bg-surface-sunken p-4">
                  <div class="flex items-center gap-4">
                    <div
                      class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl text-lg font-semibold text-white"
                      :class="avatarBgColor"
                    >
                      {{ userInitials }}
                    </div>
                    <div class="min-w-0 flex-1">
                      <div class="truncate text-base font-semibold text-ink-900">
                        {{ displayName }}
                      </div>
                      <div class="mt-1 truncate text-sm text-ink-500">
                        {{ userStore.userInfo?.email || t('settings.modal.noEmail') }}
                      </div>
                    </div>
                  </div>

                  <div class="mt-4 space-y-3">
                    <div
                      class="flex items-center justify-between gap-4 rounded-xl bg-surface px-4 py-3"
                    >
                      <span class="text-sm text-ink-500">
                        {{ t('settings.modal.username') }}
                      </span>
                      <span class="truncate text-sm font-medium text-ink-900">
                        {{ userStore.userInfo?.username || '—' }}
                      </span>
                    </div>
                    <div
                      class="flex items-center justify-between gap-4 rounded-xl bg-surface px-4 py-3"
                    >
                      <span class="text-sm text-ink-500">
                        {{ t('settings.modal.email') }}
                      </span>
                      <span class="truncate text-sm font-medium text-ink-900">
                        {{ userStore.userInfo?.email || '—' }}
                      </span>
                    </div>
                  </div>
                </div>

                <div class="rounded-2xl border border-line bg-surface p-4">
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <div class="text-sm font-semibold text-ink-900">
                        {{ t('settings.modal.language') }}
                      </div>
                      <div class="mt-1 text-sm text-ink-500">
                        {{ t('settings.modal.languageDesc') }}
                      </div>
                    </div>
                  </div>

                  <div class="mt-3 relative">
                    <select
                      :value="locale"
                      class="w-full appearance-none rounded-xl border border-line bg-surface py-2.5 pl-3 pr-9 text-sm text-ink-800 transition-colors focus:border-primary-300 focus:outline-none focus:ring-2 focus:ring-primary-100"
                      @change="selectLanguage($event.target.value)"
                    >
                      <option
                        v-for="lang in languages"
                        :key="lang.value"
                        :value="lang.value"
                      >
                        {{ lang.flag }} {{ lang.label }}
                      </option>
                    </select>
                    <div class="pointer-events-none absolute inset-y-0 right-3 flex items-center">
                      <svg class="h-4 w-4 text-ink-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                        <path d="m6 9 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
                      </svg>
                    </div>
                  </div>
                </div>

              </section>
            </div>
          </div>

          <footer
            class="flex items-center justify-between gap-3 border-t border-line px-5 py-4 sm:px-6"
          >
            <button
              type="button"
              class="rounded-xl px-3 py-2 text-sm font-medium text-ink-500 transition-colors hover:bg-line-soft hover:text-ink-900"
              @click="handleLogout"
            >
              {{ t('common.logout') }}
            </button>
            <button
              type="button"
              class="rounded-xl bg-ink-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-ink-800"
              @click="emit('close')"
            >
              {{ t('common.close') }}
            </button>
          </footer>
        </section>
      </Transition>
    </div>
  </Transition>
</template>

<script setup>
import { computed, onBeforeUnmount, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { getUiLanguageOptions } from '@/utils/languages'
import { usePreferencesStore } from '@/store/preferences'
import { useUiStore } from '@/store/ui'
import { useUserStore } from '@/store/user'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['close'])

const { t, locale } = useI18n()
const router = useRouter()
const userStore = useUserStore()
const preferencesStore = usePreferencesStore()
const uiStore = useUiStore()
const languages = computed(() => getUiLanguageOptions(t))

const displayName = computed(() => {
  const userInfo = userStore.userInfo
  if (!userInfo) return 'User'
  if (userInfo.display_name) return userInfo.display_name
  if (userInfo.first_name && userInfo.last_name) {
    return `${userInfo.first_name} ${userInfo.last_name}`
  }
  if (userInfo.first_name) return userInfo.first_name
  return userInfo.username || 'User'
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

const selectLanguage = async (language) => {
  await preferencesStore.setLanguage(language, false)
  locale.value = language
}

const handleLogout = async () => {
  await userStore.logout().catch(() => {})
  uiStore.closeSettings()
  await router.push('/login')
}

const handleKeydown = (event) => {
  if (event.key === 'Escape' && props.show) {
    uiStore.closeSettings()
  }
}

watch(
  () => props.show,
  (show) => {
    if (typeof document === 'undefined') {
      return
    }
    document.body.style.overflow = show ? 'hidden' : ''
  },
  { immediate: true }
)

if (typeof window !== 'undefined') {
  window.addEventListener('keydown', handleKeydown)
}

onBeforeUnmount(() => {
  if (typeof document !== 'undefined') {
    document.body.style.overflow = ''
  }
  if (typeof window !== 'undefined') {
    window.removeEventListener('keydown', handleKeydown)
  }
})
</script>
