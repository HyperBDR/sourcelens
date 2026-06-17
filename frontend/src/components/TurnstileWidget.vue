<template>
  <div ref="container" class="turnstile-widget"></div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'

const SCRIPT_SRC =
  'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'

const emit = defineEmits(['verified', 'expired', 'error'])

const siteKey = import.meta.env.VITE_TURNSTILE_SITE_KEY || ''
const container = ref(null)
let widgetId = null

/**
 * Load the Cloudflare Turnstile script once and resolve when ready.
 */
function loadScript() {
  if (window.turnstile) {
    return Promise.resolve()
  }
  if (window.__turnstileLoading) {
    return window.__turnstileLoading
  }
  window.__turnstileLoading = new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = SCRIPT_SRC
    script.async = true
    script.defer = true
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Turnstile script failed'))
    document.head.appendChild(script)
  })
  return window.__turnstileLoading
}

onMounted(async () => {
  // No site key configured: bypass (development) so the flow is usable.
  if (!siteKey) {
    emit('verified', '')
    return
  }

  try {
    await loadScript()
    widgetId = window.turnstile.render(container.value, {
      sitekey: siteKey,
      callback: (token) => emit('verified', token),
      'expired-callback': () => emit('expired'),
      'error-callback': () => emit('error')
    })
  } catch (err) {
    emit('error', err)
  }
})

/**
 * Reset the widget so the user can solve the challenge again.
 */
function reset() {
  if (siteKey && widgetId !== null && window.turnstile) {
    window.turnstile.reset(widgetId)
  }
}

onBeforeUnmount(() => {
  if (siteKey && widgetId !== null && window.turnstile) {
    window.turnstile.remove(widgetId)
  }
})

defineExpose({ reset, hasSiteKey: !!siteKey })
</script>

<style scoped>
.turnstile-widget {
  display: flex;
  justify-content: center;
  min-height: 0;
}
</style>
