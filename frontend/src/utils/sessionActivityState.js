export function createSessionActivityController(state) {
  const notificationTimers = new Map()
  let nextActivityId = 0
  let nextNotificationId = 0

  function beginActivity(sessionUuid, activityId) {
    if (!sessionUuid || !activityId) return
    const activities = state.activities[sessionUuid] || []
    if (!activities.includes(activityId)) {
      state.activities[sessionUuid] = [...activities, activityId]
    }
  }

  function endActivity(sessionUuid, activityId) {
    const activities = state.activities[sessionUuid] || []
    const remaining = activities.filter((item) => item !== activityId)
    if (remaining.length) {
      state.activities[sessionUuid] = remaining
    } else {
      delete state.activities[sessionUuid]
    }
  }

  function hasActivity(sessionUuid) {
    return Boolean(state.activities[sessionUuid]?.length)
  }

  function createActivityId(prefix = 'activity') {
    nextActivityId += 1
    return `${prefix}:${nextActivityId}`
  }

  function dismissNotification(id) {
    const timer = notificationTimers.get(id)
    if (timer) {
      clearTimeout(timer)
      notificationTimers.delete(id)
    }
    state.notifications = state.notifications.filter((item) => item.id !== id)
  }

  function notify(options) {
    nextNotificationId += 1
    const notification = {
      id: nextNotificationId,
      message: '',
      title: '',
      type: 'success',
      ...options
    }
    state.notifications.push(notification)
    const duration = options.duration || 5000
    const timer = setTimeout(() => {
      dismissNotification(notification.id)
    }, duration)
    notificationTimers.set(notification.id, timer)
    return notification.id
  }

  function setUnreadSessions(unreadSessions) {
    state.unreadSessions = { ...unreadSessions }
  }

  function clearSessionActivity() {
    state.activities = {}
    state.notifications = []
    notificationTimers.forEach((timer) => clearTimeout(timer))
    notificationTimers.clear()
  }

  return {
    beginActivity,
    clearSessionActivity,
    createActivityId,
    dismissNotification,
    endActivity,
    hasActivity,
    notify,
    setUnreadSessions,
    state
  }
}
