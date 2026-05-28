<template>
  <div class="bg-white rounded border border-gray-200 shadow-sm p-3">
    <div class="flex items-center gap-3">
      <div
        :class="avatarBgColor"
        class="w-12 h-12 rounded-full flex items-center justify-center flex-shrink-0"
      >
        <span class="text-white font-medium text-lg">
          {{ userInitials }}
        </span>
      </div>
      <div class="flex-1 min-w-0">
        <div class="text-lg font-semibold text-gray-900 truncate">
          {{ displayName }}
        </div>
        <div class="text-sm text-gray-500 truncate">
          {{ userStore.userInfo?.email || '' }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useUserStore } from '@/store/user'

const userStore = useUserStore()

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
  // Extract first character from display name
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
</script>
