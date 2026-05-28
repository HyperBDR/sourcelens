<template>
  <div v-if="platforms.length > 1" class="relative" ref="switcherRef">
    <button
      @click="open = !open"
      class="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium shadow-sm transition-colors"
      :class="[buttonClasses, buttonClass]"
    >
      <span class="max-w-[20rem] truncate whitespace-nowrap">{{
        currentPlatform?.label || t('platforms.switchPlatform')
      }}</span>
      <svg
        class="h-4 w-4 transition-transform"
        :class="{ 'rotate-180': open }"
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

    <Transition
      enter-active-class="transition ease-out duration-100"
      enter-from-class="transform opacity-0 scale-95"
      enter-to-class="transform opacity-100 scale-100"
      leave-active-class="transition ease-in duration-75"
      leave-from-class="transform opacity-100 scale-100"
      leave-to-class="transform opacity-0 scale-95"
    >
      <div
        v-if="open"
        class="absolute right-0 z-50 mt-2 w-80 overflow-hidden rounded-xl shadow-lg"
        :class="panelClasses"
      >
        <div
          class="border-b px-4 py-3 text-xs font-semibold uppercase tracking-wide"
          :class="headerClasses"
        >
          {{ t('platforms.switchPlatform') }}
        </div>
        <router-link
          v-for="platform in platforms"
          :key="platform.key"
          :to="platform.defaultPath"
          class="flex items-center justify-between px-4 py-3 text-sm transition-colors"
          :class="itemClasses"
          @click="open = false"
        >
          <span class="min-w-0 flex-1 truncate whitespace-nowrap pr-2">{{
            platform.label
          }}</span>
          <span
            v-if="platform.key === currentPlatformKey"
            class="rounded-full bg-primary-50 px-2 py-0.5 text-xs font-medium text-primary-700"
          >
            {{ t('common.current') }}
          </span>
        </router-link>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/store/user'
import {
  getAvailablePlatforms,
  getCurrentPlatformKey
} from '@/utils/platformAccess'

const props = defineProps({
  variant: {
    type: String,
    default: 'light'
  },
  buttonClass: {
    type: String,
    default: ''
  }
})

const { t } = useI18n()
const route = useRoute()
const userStore = useUserStore()

const open = ref(false)
const switcherRef = ref(null)

const platforms = computed(() => getAvailablePlatforms(userStore.userInfo, t))
const currentPlatformKey = computed(() => getCurrentPlatformKey(route.path))
const currentPlatform = computed(
  () =>
    platforms.value.find((item) => item.key === currentPlatformKey.value) ||
    platforms.value[0] ||
    null
)

const isDark = computed(() => props.variant === 'dark')

const buttonClasses = computed(() =>
  isDark.value
    ? 'border border-slate-600 bg-slate-800 text-slate-100 hover:border-slate-500 hover:bg-slate-700'
    : 'border border-gray-200 bg-white text-gray-700 hover:border-primary-300 hover:text-primary-700'
)

const panelClasses = computed(() =>
  isDark.value
    ? 'border border-gray-200 bg-white'
    : 'border border-gray-200 bg-white'
)

const headerClasses = computed(() =>
  isDark.value
    ? 'border-gray-100 text-gray-500'
    : 'border-gray-100 text-gray-500'
)

const itemClasses = computed(() =>
  isDark.value
    ? 'text-gray-700 hover:bg-gray-50 hover:text-gray-900'
    : 'text-gray-700 hover:bg-gray-50 hover:text-gray-900'
)

const handleClickOutside = (event) => {
  if (switcherRef.value && !switcherRef.value.contains(event.target)) {
    open.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>
