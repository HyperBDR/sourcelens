<template>
  <div id="app" class="min-h-screen bg-surface-sunken">
    <ErrorBoundary>
      <router-view />
    </ErrorBoundary>
    <Teleport to="body">
      <UserSettingsModal
        :show="uiStore.settingsOpen"
        @close="uiStore.closeSettings()"
      />
    </Teleport>
    <ActivityNotificationStack />
    <Toast />
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { useSessionActivity } from '@/composables/useSessionActivity'
import { useUserStore } from '@/store/user'
import { useUiStore } from '@/store/ui'
import { usePreferencesStore } from '@/store/preferences'
import ErrorBoundary from '@/components/ui/ErrorBoundary.vue'
import ActivityNotificationStack from '@/components/ui/ActivityNotificationStack.vue'
import Toast from '@/components/ui/Toast.vue'
import UserSettingsModal from '@/components/settings/UserSettingsModal.vue'
import {
  answerCompletionTitle,
  readUnreadSessions,
  UNREAD_STORAGE_KEY
} from '@/utils/answerCompletionNotifications'
import { stopRunCompletionTracking } from '@/utils/runCompletionTracking'

const { t } = useI18n()
const userStore = useUserStore()
const uiStore = useUiStore()
const preferencesStore = usePreferencesStore()
const sessionActivity = useSessionActivity()
const baseDocumentTitle = document.title || 'SourceLens'

function refreshUnreadSessions() {
  sessionActivity.setUnreadSessions(readUnreadSessions(window.localStorage))
}

function refreshDocumentTitle() {
  const hasUnread =
    Boolean(userStore.token) &&
    preferencesStore.answerCompletionIndicator &&
    Object.keys(sessionActivity.state.unreadSessions).length > 0
  document.title = answerCompletionTitle({
    baseTitle: baseDocumentTitle,
    completionLabel: t('lens.chat.tabAnswerCompleted'),
    hasUnread
  })
}

function handleCompletionStorage(event) {
  if (event.key === UNREAD_STORAGE_KEY) {
    refreshUnreadSessions()
  }
  if (event.key === 'answerCompletionIndicator') {
    preferencesStore.answerCompletionIndicator = event.newValue !== 'false'
  }
  if (event.key === 'nativeBrowserNotifications') {
    preferencesStore.nativeBrowserNotifications = event.newValue === 'true'
  }
}

watch(
  [
    () => preferencesStore.currentLanguage,
    () => Object.keys(sessionActivity.state.unreadSessions).join(','),
    () => userStore.token
  ],
  refreshDocumentTitle
)

watch(
  () => preferencesStore.answerCompletionIndicator,
  () => {
    refreshUnreadSessions()
    refreshDocumentTitle()
  }
)

watch(
  () => userStore.token,
  (token, previousToken) => {
    if (previousToken && token !== previousToken) {
      stopRunCompletionTracking()
      sessionActivity.clearSessionActivity()
    }
  }
)

// Initialize app
onMounted(() => {
  window.addEventListener('storage', handleCompletionStorage)
  refreshUnreadSessions()
  refreshDocumentTitle()
  // Check if user is logged in, but only if we have a token and user is not loaded
  // This avoids duplicate calls with router guard
  const hasToken = !!localStorage.getItem('access_token')
  if (hasToken && !userStore.user) {
    userStore.checkAuth().catch(() => {
      // Error handling is done in checkAuth (clears auth state)
    })
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('storage', handleCompletionStorage)
})
</script>
