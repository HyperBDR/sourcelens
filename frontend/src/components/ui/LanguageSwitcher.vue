<template>
  <div class="relative" ref="dropdownRef">
    <button
      @click="toggleDropdown"
      :class="[
        'flex items-center gap-1.5 rounded-md px-2 py-1 text-sm transition-colors',
        variant === 'dark'
          ? 'text-white hover:bg-white/10'
          : 'text-ink-600 hover:bg-line-soft hover:text-ink-900'
      ]"
      :title="t('common.language')"
    >
      <!-- Language icon -->
      <svg
        class="w-4 h-4"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        xmlns="http://www.w3.org/2000/svg"
      >
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"
        />
      </svg>
      <!-- Current language flag/name -->
      <span class="text-xs font-medium">{{ currentLanguageDisplay }}</span>
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
        v-if="showDropdown"
        class="absolute right-0 z-50 mt-2 w-32 overflow-hidden rounded-lg border border-line bg-surface shadow-lg"
      >
        <button
          v-for="lang in languages"
          :key="lang.value"
          @click="selectLanguage(lang.value)"
          class="flex w-full items-center px-3 py-2 text-sm text-ink-700 transition-colors hover:bg-line-soft"
          :class="{ 'bg-line-soft font-medium text-ink-900': locale === lang.value }"
        >
          <span class="mr-2 text-sm">{{ lang.flag }}</span>
          {{ lang.label }}
        </button>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePreferencesStore } from '@/store/preferences'
import { getUiLanguageOptions } from '@/utils/languages'

defineProps({
  variant: {
    type: String,
    default: 'default',
    validator: (v) => ['default', 'dark'].includes(v)
  }
})

const { t, locale } = useI18n()
const preferencesStore = usePreferencesStore()

const showDropdown = ref(false)
const dropdownRef = ref(null)

const languages = computed(() => getUiLanguageOptions(t))

const currentLanguageDisplay = computed(() => {
  const lang = languages.value.find((l) => l.value === locale.value)
  return lang ? lang.flag : '🌐'
})

const toggleDropdown = () => {
  showDropdown.value = !showDropdown.value
}

const selectLanguage = async (language) => {
  // Only update UI display language, do not sync to backend Profile
  // Profile.language is for AI generation and backend logic, not UI display
  await preferencesStore.setLanguage(language, false)
  locale.value = language
  showDropdown.value = false
}

const handleClickOutside = (event) => {
  if (dropdownRef.value && !dropdownRef.value.contains(event.target)) {
    showDropdown.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>
