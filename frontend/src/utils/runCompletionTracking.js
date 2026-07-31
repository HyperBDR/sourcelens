import { useSessionActivity } from '../composables/useSessionActivity.js'
import { pollRunUntilTerminal } from './answerCompletionNotifications.js'

const trackers = new Map()

export function startRunCompletionTracking(options) {
  if (!options.run?.uuid || trackers.has(options.run.uuid)) {
    return false
  }

  const activity = useSessionActivity()
  const activityId = `run:${options.run.uuid}`
  const tracker = { stopped: false }
  let activityEnded = false
  trackers.set(options.run.uuid, tracker)
  activity.beginActivity(options.sessionUuid, activityId)

  void pollRunUntilTerminal({
    getRun: options.getRun,
    initialRun: options.run,
    isStopped: () => tracker.stopped,
    maxAttempts: options.maxAttempts,
    runUuid: options.run.uuid,
    sleep: options.sleep
  })
    .then((terminalRun) => {
      if (terminalRun && !tracker.stopped) {
        activity.endActivity(options.sessionUuid, activityId)
        activityEnded = true
        return options.onTerminal(terminalRun)
      }
      return null
    })
    .finally(() => {
      if (!activityEnded) {
        activity.endActivity(options.sessionUuid, activityId)
      }
      trackers.delete(options.run.uuid)
    })
  return true
}

export function stopRunCompletionTracking() {
  trackers.forEach((tracker) => {
    tracker.stopped = true
  })
  trackers.clear()
}
