<script setup>
import { onUnmounted, ref, watch } from 'vue'

import api from '@/api'

const props = defineProps({
  // Either a local blob:/data: URL (optimistic preview) or an
  // authenticated API path like /api/lens/attachments/<uuid>/.
  src: { type: String, default: '' },
  alt: { type: String, default: '' },
  // When true, clicking the image opens a full-screen lightbox.
  zoomable: { type: Boolean, default: false }
})

const resolved = ref('')
const failed = ref(false)
const zoomed = ref(false)
let objectUrl = ''

function cleanup() {
  if (objectUrl) {
    URL.revokeObjectURL(objectUrl)
    objectUrl = ''
  }
}

async function load(src) {
  cleanup()
  failed.value = false
  if (!src) {
    resolved.value = ''
    return
  }
  if (src.startsWith('blob:') || src.startsWith('data:')) {
    resolved.value = src
    return
  }
  try {
    // api client baseURL already ends with /api; drop the leading prefix.
    const path = src.replace(/^\/api/, '')
    const response = await api.get(path, { responseType: 'blob' })
    objectUrl = URL.createObjectURL(response.data)
    resolved.value = objectUrl
  } catch {
    failed.value = true
    resolved.value = ''
  }
}

function openZoom() {
  if (props.zoomable && resolved.value) {
    zoomed.value = true
  }
}

function closeZoom() {
  zoomed.value = false
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    closeZoom()
  }
}

watch(zoomed, (open) => {
  if (open) {
    document.addEventListener('keydown', onKeydown)
    document.body.style.overflow = 'hidden'
  } else {
    document.removeEventListener('keydown', onKeydown)
    document.body.style.overflow = ''
  }
})

watch(() => props.src, load, { immediate: true })

onUnmounted(() => {
  cleanup()
  document.removeEventListener('keydown', onKeydown)
  document.body.style.overflow = ''
})
</script>

<template>
  <img
    v-if="resolved"
    :src="resolved"
    :alt="alt"
    class="auth-image"
    :class="{ 'is-zoomable': zoomable }"
    loading="lazy"
    @click="openZoom"
  />
  <div v-else-if="failed" class="auth-image auth-image-failed">⚠</div>

  <Teleport to="body">
    <div v-if="zoomed" class="lightbox-backdrop" @click="closeZoom">
      <button
        type="button"
        class="lightbox-close"
        aria-label="close"
        @click.stop="closeZoom"
      >
        ×
      </button>
      <img :src="resolved" :alt="alt" class="lightbox-img" @click.stop />
    </div>
  </Teleport>
</template>

<style scoped>
.auth-image {
  display: block;
  max-width: 100%;
  height: auto;
  border-radius: 8px;
}
.auth-image.is-zoomable {
  cursor: zoom-in;
}
.auth-image-failed {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  background: #f3f4f6;
  color: #9ca3af;
  font-size: 20px;
}
.lightbox-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4vh 4vw;
  background: rgba(0, 0, 0, 0.8);
  cursor: zoom-out;
}
.lightbox-img {
  max-width: 92vw;
  max-height: 92vh;
  object-fit: contain;
  border-radius: 6px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.5);
  cursor: default;
}
.lightbox-close {
  position: fixed;
  top: 16px;
  right: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: 9999px;
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  font-size: 26px;
  line-height: 1;
}
.lightbox-close:hover {
  background: rgba(255, 255, 255, 0.28);
}
</style>
