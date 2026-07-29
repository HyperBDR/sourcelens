const TRANSITION_FALLBACK_DELAY = 100

const KEYFRAMES = {
  enter: {
    backdrop: [{ opacity: 0 }, { opacity: 1 }],
    panel: [{ transform: 'translateX(100%)' }, { transform: 'translateX(0)' }]
  },
  leave: {
    backdrop: [{ opacity: 1 }, { opacity: 0 }],
    panel: [{ transform: 'translateX(0)' }, { transform: 'translateX(100%)' }]
  }
}

export function runDrawerTransition(element, direction, duration, done) {
  if (element.ownerDocument?.hidden) {
    done()
    return
  }

  const panel = element.querySelector('[data-drawer-panel]')
  if (typeof element.animate !== 'function' || !panel) {
    done()
    return
  }

  const easing =
    direction === 'enter'
      ? 'cubic-bezier(0, 0, 0.2, 1)'
      : 'cubic-bezier(0.4, 0, 1, 1)'
  const options = { duration, easing, fill: 'both' }
  const frames = KEYFRAMES[direction]
  const animations = [
    element.animate(frames.backdrop, options),
    panel.animate(frames.panel, options)
  ]
  let completed = false

  const complete = () => {
    if (completed) return
    completed = true
    clearTimeout(fallbackTimer)
    animations.forEach((animation) => animation.cancel())
    done()
  }
  const fallbackTimer = setTimeout(
    complete,
    duration + TRANSITION_FALLBACK_DELAY
  )

  Promise.allSettled(animations.map((animation) => animation.finished)).then(
    complete
  )
}
