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
      <div class="absolute inset-0 bg-black/30 backdrop-blur-[2px]" />

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
          class="relative flex h-[480px] max-h-[82vh] w-full max-w-2xl overflow-hidden rounded-2xl border border-line bg-surface shadow-soft-lg"
        >
          <!-- Left nav -->
          <nav
            class="flex w-14 shrink-0 flex-col border-r border-line bg-surface-sunken py-3 sm:w-44"
          >
            <div class="hidden px-3 pb-2 pt-1 sm:block">
              <div
                class="text-xs font-semibold uppercase tracking-wide text-theme-subtle"
              >
                {{ t('settings.modal.label') }}
              </div>
            </div>

            <div class="flex-1 space-y-0.5 px-2">
              <button
                v-for="section in sections"
                :key="section.key"
                type="button"
                class="flex w-full items-center justify-center gap-2.5 rounded-lg px-2 py-2 text-left text-sm transition-colors sm:justify-start sm:px-3"
                :aria-label="section.label"
                :class="
                  activeSection === section.key
                    ? 'bg-surface font-medium text-theme shadow-sm'
                    : 'text-theme-secondary hover:bg-surface-hover hover:text-theme'
                "
                @click="activeSection = section.key"
              >
                <component :is="section.icon" class="h-4 w-4 shrink-0" />
                <span class="hidden min-w-0 flex-1 truncate sm:block">
                  {{ section.label }}
                </span>
                <span
                  v-if="
                    section.key === 'release-notes' &&
                    uiStore.hasUnreadReleaseNotes
                  "
                  class="h-2 w-2 shrink-0 rounded-full bg-primary-500"
                >
                  <span class="sr-only">
                    {{ t('settings.modal.releaseNotesUnread') }}
                  </span>
                </span>
              </button>
            </div>

            <div class="border-t border-line px-2 pt-2">
              <button
                type="button"
                class="flex w-full items-center justify-center gap-2.5 rounded-lg px-2 py-2 text-left text-sm text-red-500 transition-colors hover:bg-red-50 hover:text-red-600 sm:justify-start sm:px-3"
                :aria-label="t('common.logout')"
                @click="handleLogout"
              >
                <svg
                  class="h-4 w-4 shrink-0"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                  aria-hidden="true"
                >
                  <path
                    d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                  <polyline
                    points="16 17 21 12 16 7"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                  <line x1="21" y1="12" x2="9" y2="12" stroke-linecap="round" />
                </svg>
                <span class="hidden sm:block">{{ t('common.logout') }}</span>
              </button>
            </div>
          </nav>

          <!-- Right content -->
          <div class="flex min-w-0 flex-1 flex-col">
            <header
              class="flex items-center justify-between border-b border-line px-4 py-4 sm:px-5"
            >
              <h2 class="text-base font-semibold text-theme">
                {{ sections.find((s) => s.key === activeSection)?.label }}
              </h2>
              <button
                type="button"
                class="flex h-8 w-8 items-center justify-center rounded-full text-theme-subtle transition-colors hover:bg-surface-hover hover:text-theme-secondary"
                :aria-label="t('common.close')"
                @click="emit('close')"
              >
                <svg
                  class="h-4 w-4"
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

            <div class="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-5">
              <!-- Profile section -->
              <div v-if="activeSection === 'profile'" class="space-y-5">
                <div class="flex items-center gap-4">
                  <div
                    class="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl text-xl font-semibold text-white"
                    :class="avatarBgColor"
                  >
                    {{ userInitials }}
                  </div>
                  <div class="min-w-0">
                    <div class="truncate text-base font-semibold text-theme">
                      {{ displayName }}
                    </div>
                    <div class="mt-0.5 truncate text-sm text-theme-muted">
                      {{
                        userStore.userInfo?.email || t('settings.modal.noEmail')
                      }}
                    </div>
                  </div>
                </div>

                <div class="divide-y divide-line rounded-xl border border-line">
                  <div class="flex items-center justify-between px-4 py-3">
                    <span class="text-sm text-theme-muted">{{
                      t('settings.modal.username')
                    }}</span>
                    <span class="text-sm font-medium text-theme">
                      {{ userStore.userInfo?.username || '—' }}
                    </span>
                  </div>
                  <div class="flex items-center justify-between px-4 py-3">
                    <span class="text-sm text-theme-muted">{{
                      t('settings.modal.email')
                    }}</span>
                    <span class="text-sm font-medium text-theme">
                      {{ userStore.userInfo?.email || '—' }}
                    </span>
                  </div>
                </div>
              </div>

              <!-- Language section -->
              <div v-if="activeSection === 'language'" class="space-y-3">
                <p class="text-sm text-theme-muted">
                  {{ t('settings.modal.languageDesc') }}
                </p>
                <div class="relative">
                  <BaseSelect
                    id="ui-language"
                    :model-value="locale"
                    @change="selectLanguage($event.target.value)"
                  >
                    <option
                      v-for="lang in languages"
                      :key="lang.value"
                      :value="lang.value"
                    >
                      {{ lang.flag }} {{ lang.label }}
                    </option>
                  </BaseSelect>
                  <div
                    class="pointer-events-none absolute inset-y-0 right-3 flex items-center"
                  >
                    <svg
                      class="h-4 w-4 text-theme-subtle"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.5"
                    >
                      <path
                        d="m6 9 6 6 6-6"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </div>
                </div>
              </div>

              <!-- Appearance section -->
              <div v-if="activeSection === 'appearance'" class="space-y-3">
                <p class="text-sm text-theme-muted">
                  {{ t('settings.modal.appearanceDesc') }}
                </p>
                <div class="space-y-2" role="radiogroup">
                  <label
                    v-for="option in themeOptions"
                    :key="option.value"
                    class="flex cursor-pointer items-center gap-3 rounded-xl border border-line px-4 py-3 text-sm text-theme transition-colors hover:bg-surface-hover"
                  >
                    <input
                      v-model="preferencesStore.themeMode"
                      type="radio"
                      name="appearance-mode"
                      :value="option.value"
                      class="h-4 w-4 accent-primary-500"
                      @change="preferencesStore.setThemeMode(option.value)"
                    />
                    <span class="font-medium">{{ option.label }}</span>
                  </label>
                </div>
                <p
                  v-if="preferencesStore.themeMode === 'scheduled'"
                  class="text-sm text-theme-muted"
                >
                  {{ t('settings.modal.themeScheduleDescription') }}
                </p>
              </div>

              <AnswerNotificationSettings
                v-if="activeSection === 'notifications'"
              />

              <ReleaseNotesSettings v-if="activeSection === 'release-notes'" />

              <PasswordChangeSettings v-if="activeSection === 'security'" />
            </div>
          </div>
        </section>
      </Transition>
    </div>
  </Transition>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import AnswerNotificationSettings from '@/components/settings/AnswerNotificationSettings.vue'
import PasswordChangeSettings from '@/components/settings/PasswordChangeSettings.vue'
import ReleaseNotesSettings from '@/components/settings/ReleaseNotesSettings.vue'
import BaseSelect from '@/components/ui/BaseSelect.vue'
import { getPasswordManagementText } from '@/locales/passwordManagement'
import { getUiLanguageOptions } from '@/utils/languages'
import { usePreferencesStore } from '@/store/preferences'
import { useUiStore } from '@/store/ui'
import { useUserStore } from '@/store/user'

const props = defineProps({
  show: { type: Boolean, default: false }
})

const emit = defineEmits(['close'])

const { t, locale } = useI18n()
const router = useRouter()
const userStore = useUserStore()
const uiStore = useUiStore()
const preferencesStore = usePreferencesStore()
const languages = computed(() => getUiLanguageOptions(t))
const activeSection = ref('profile')

const themeOptions = computed(() => [
  { value: 'light', label: t('settings.modal.themeLight') },
  { value: 'dark', label: t('settings.modal.themeDark') },
  { value: 'system', label: t('settings.modal.themeSystem') },
  { value: 'scheduled', label: t('settings.modal.themeScheduled') }
])

const UserIcon = {
  template: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" stroke-linecap="round"/></svg>`
}
const GlobeIcon = {
  template: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3.6 9h16.8M3.6 15h16.8M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" stroke-linecap="round"/></svg>`
}
const AppearanceIcon = {
  template: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 3v18" stroke-linecap="round"/><path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" fill-opacity="0.25"/></svg>`
}
const BellIcon = {
  template: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 21h4" stroke-linecap="round"/></svg>`
}
const ReleaseNotesIcon = {
  template: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M5 4h14v16H5z"/><path d="M8 8h8M8 12h8M8 16h5" stroke-linecap="round"/></svg>`
}
const LockIcon = {
  template: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3" stroke-linecap="round"/></svg>`
}

const sections = computed(() => [
  { key: 'profile', label: t('settings.modal.title'), icon: UserIcon },
  {
    key: 'release-notes',
    label: t('settings.modal.releaseNotes'),
    icon: ReleaseNotesIcon
  },
  { key: 'language', label: t('settings.modal.language'), icon: GlobeIcon },
  {
    key: 'appearance',
    label: t('settings.modal.appearance'),
    icon: AppearanceIcon
  },
  {
    key: 'notifications',
    label: t('settings.modal.notifications'),
    icon: BellIcon
  },
  {
    key: 'security',
    label: getPasswordManagementText(locale.value).security.title,
    icon: LockIcon
  }
])

const displayName = computed(() => {
  const userInfo = userStore.userInfo
  if (!userInfo) return 'User'
  if (userInfo.display_name) return userInfo.display_name
  if (userInfo.first_name && userInfo.last_name)
    return `${userInfo.first_name} ${userInfo.last_name}`
  if (userInfo.first_name) return userInfo.first_name
  return userInfo.username || 'User'
})

const userInitials = computed(
  () => displayName.value.trim().charAt(0).toUpperCase() || 'U'
)

const avatarBgColor = computed(() => {
  const colors = [
    'bg-blue-500',
    'bg-indigo-500',
    'bg-emerald-500',
    'bg-rose-500',
    'bg-amber-500',
    'bg-cyan-500'
  ]
  return colors[userInitials.value.charCodeAt(0) % colors.length]
})

const selectLanguage = async (language) => {
  await userStore.updateLanguage(language)
}

const handleLogout = async () => {
  await userStore.logout().catch(() => {})
  uiStore.closeSettings()
  await router.push('/login')
}

const handleKeydown = (event) => {
  if (event.key === 'Escape' && props.show) uiStore.closeSettings()
}

watch(
  () => props.show,
  (show) => {
    if (show) activeSection.value = uiStore.settingsTab || 'profile'
    if (typeof document !== 'undefined')
      document.body.style.overflow = show ? 'hidden' : ''
  },
  { immediate: true }
)

watch(
  [() => props.show, activeSection],
  ([show, section]) => {
    if (show && section === 'release-notes') {
      uiStore.markReleaseNotesViewed()
    }
  },
  { immediate: true }
)

if (typeof window !== 'undefined')
  window.addEventListener('keydown', handleKeydown)

onBeforeUnmount(() => {
  if (typeof document !== 'undefined') document.body.style.overflow = ''
  if (typeof window !== 'undefined')
    window.removeEventListener('keydown', handleKeydown)
})
</script>
