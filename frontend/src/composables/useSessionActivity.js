import { reactive } from 'vue'

import { createSessionActivityController } from '@/utils/sessionActivityState'

const state = reactive({
  activities: {},
  notifications: [],
  unreadSessions: {}
})

const controller = createSessionActivityController(state)

export function useSessionActivity() {
  return controller
}
