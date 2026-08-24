export function createStreamTextBuffer({
  onFlush,
  schedule = (callback) => requestAnimationFrame(callback),
  cancel = (frame) => cancelAnimationFrame(frame)
}) {
  let pending = ''
  let frame = null

  function flush() {
    if (frame !== null) {
      cancel(frame)
      frame = null
    }
    if (!pending) return
    const chunk = pending
    pending = ''
    onFlush(chunk)
  }

  function flushFrame() {
    frame = null
    flush()
  }

  return {
    push(text) {
      pending += String(text || '')
      if (pending && frame === null) {
        frame = schedule(flushFrame)
      }
    },
    flush,
    clear() {
      if (frame !== null) {
        cancel(frame)
        frame = null
      }
      pending = ''
    }
  }
}
