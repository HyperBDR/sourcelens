let activeLocks = 0
let previousBodyOverflow = ''
const activeDialogs = []

export function acquireBodyScrollLock() {
  if (typeof document === 'undefined') return

  if (activeLocks === 0) {
    previousBodyOverflow = document.body.style.overflow
  }
  activeLocks += 1
  document.body.style.overflow = 'hidden'
}

export function releaseBodyScrollLock() {
  if (typeof document === 'undefined' || activeLocks === 0) return

  activeLocks -= 1
  if (activeLocks === 0) {
    document.body.style.overflow = previousBodyOverflow
    previousBodyOverflow = ''
  }
}

export function registerDialog(dialog) {
  unregisterDialog(dialog)
  activeDialogs.push(dialog)
}

export function unregisterDialog(dialog) {
  const index = activeDialogs.indexOf(dialog)
  if (index !== -1) {
    activeDialogs.splice(index, 1)
  }
}

export function isTopDialog(dialog) {
  return activeDialogs.at(-1) === dialog
}
