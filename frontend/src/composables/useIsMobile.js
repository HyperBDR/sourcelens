import { onMounted, onUnmounted, ref } from 'vue'

export const MOBILE_BREAKPOINT = 1024

/**
 * Reactive viewport-width check that updates on resize / orientation
 * change. Replaces ad-hoc `computed(() => window.innerWidth < N)`, which
 * never recomputes (innerWidth is not reactive) and so freezes the
 * mobile/desktop state at first render.
 */
export function useIsMobile(breakpoint = MOBILE_BREAKPOINT) {
  const isMobile = ref(
    typeof window !== 'undefined' && window.innerWidth < breakpoint
  )

  let media = null
  const sync = () => {
    if (media) {
      isMobile.value = media.matches
    }
  }

  onMounted(() => {
    if (typeof window === 'undefined' || !window.matchMedia) {
      return
    }
    media = window.matchMedia(`(max-width: ${breakpoint - 1}px)`)
    sync()
    media.addEventListener('change', sync)
  })

  onUnmounted(() => {
    if (media) {
      media.removeEventListener('change', sync)
    }
  })

  return { isMobile }
}
