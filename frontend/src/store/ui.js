import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUiStore = defineStore('ui', () => {
  const adminSidebarScrollTop = ref(0)
  const settingsOpen = ref(false)
  const settingsTab = ref('profile')

  const openSettings = (tab = 'profile') => {
    settingsTab.value = tab
    settingsOpen.value = true
  }

  const closeSettings = () => {
    settingsOpen.value = false
  }

  return {
    adminSidebarScrollTop,
    settingsOpen,
    settingsTab,
    openSettings,
    closeSettings
  }
})
