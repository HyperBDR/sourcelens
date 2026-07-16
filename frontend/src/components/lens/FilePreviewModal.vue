<script setup>
import { onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Download, X } from '@lucide/vue'

import MarkdownRenderer from '@/components/ui/MarkdownRenderer.vue'
import { fetchDeliverableBlob, previewKind } from '@/utils/filePreview'

const props = defineProps({
  // The delivered file to preview, or null when the modal is closed.
  file: { type: Object, default: null }
})

const emit = defineEmits(['close', 'download'])

const { t } = useI18n()

const kind = ref('')
const objectUrl = ref('')
const textContent = ref('')
const loading = ref(false)
const failed = ref(false)
let currentUrl = ''
let loadSeq = 0

function cleanup() {
  if (currentUrl) {
    URL.revokeObjectURL(currentUrl)
    currentUrl = ''
  }
  objectUrl.value = ''
  textContent.value = ''
}

async function load(file) {
  // Bump the sequence so any in-flight load resolving later is discarded;
  // this prevents leaked object URLs and cross-file renders on rapid
  // preview switches.
  const seq = ++loadSeq
  cleanup()
  failed.value = false
  if (!file) {
    kind.value = ''
    return
  }
  kind.value = previewKind(file)
  if (!kind.value) {
    failed.value = true
    return
  }
  loading.value = true
  try {
    const blob = await fetchDeliverableBlob(file)
    if (seq !== loadSeq) {
      return
    }
    if (kind.value === 'text' || kind.value === 'markdown') {
      const text = await blob.text()
      if (seq !== loadSeq) {
        return
      }
      textContent.value = text
    } else {
      const url = URL.createObjectURL(blob)
      if (seq !== loadSeq) {
        URL.revokeObjectURL(url)
        return
      }
      currentUrl = url
      objectUrl.value = url
    }
  } catch {
    if (seq === loadSeq) {
      failed.value = true
    }
  } finally {
    if (seq === loadSeq) {
      loading.value = false
    }
  }
}

function close() {
  emit('close')
}

function onDownload() {
  if (props.file) {
    emit('download', props.file)
  }
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    close()
  }
}

let locked = false
let prevOverflow = ''

function lockScroll() {
  if (!locked) {
    prevOverflow = document.body.style.overflow
    locked = true
  }
  document.body.style.overflow = 'hidden'
}

function unlockScroll() {
  if (locked) {
    document.body.style.overflow = prevOverflow
    locked = false
  }
}

watch(
  () => props.file,
  (file) => {
    load(file)
    if (file) {
      document.addEventListener('keydown', onKeydown)
      lockScroll()
    } else {
      document.removeEventListener('keydown', onKeydown)
      unlockScroll()
    }
  },
  { immediate: true }
)

onUnmounted(() => {
  cleanup()
  document.removeEventListener('keydown', onKeydown)
  unlockScroll()
})
</script>

<template>
  <Teleport to="body">
    <div v-if="file" class="preview-backdrop" @click="close">
      <div class="preview-panel" @click.stop>
        <header class="preview-header">
          <span class="preview-title" :title="file.filename">
            {{ file.filename }}
          </span>
          <div class="preview-tools">
            <button
              type="button"
              class="preview-tool"
              :title="t('lens.chat.download')"
              @click="onDownload"
            >
              <Download :size="18" />
            </button>
            <button
              type="button"
              class="preview-tool"
              :aria-label="t('common.close')"
              @click="close"
            >
              <X :size="18" />
            </button>
          </div>
        </header>

        <div class="preview-body">
          <div v-if="loading" class="preview-status">
            {{ t('lens.chat.previewLoading') }}
          </div>
          <div v-else-if="failed" class="preview-status">
            {{ t('lens.chat.previewFailed') }}
          </div>

          <img
            v-else-if="kind === 'image'"
            :src="objectUrl"
            :alt="file.filename"
            class="preview-image"
          />

          <iframe
            v-else-if="kind === 'pdf'"
            :src="objectUrl"
            :title="file.filename"
            class="preview-frame"
          ></iframe>

          <iframe
            v-else-if="kind === 'html'"
            :src="objectUrl"
            :title="file.filename"
            class="preview-frame"
            sandbox=""
          ></iframe>

          <MarkdownRenderer
            v-else-if="kind === 'markdown'"
            :content="textContent"
            class="preview-markdown"
          />

          <pre v-else-if="kind === 'text'" class="preview-text">{{
            textContent
          }}</pre>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.preview-backdrop {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 4vh 4vw;
  background: rgba(0, 0, 0, 0.7);
}
.preview-panel {
  display: flex;
  flex-direction: column;
  width: 100%;
  max-width: 960px;
  height: 100%;
  max-height: 90vh;
  overflow: hidden;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.4);
}
.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid #eceff3;
}
.preview-title {
  min-width: 0;
  overflow: hidden;
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview-tools {
  display: flex;
  flex-shrink: 0;
  gap: 4px;
}
.preview-tool {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  color: #6b7280;
  border-radius: 8px;
  transition: all 0.15s;
}
.preview-tool:hover {
  color: #2563eb;
  background: #eff6ff;
}
.preview-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: #f8fafc;
}
.preview-status {
  padding: 48px 16px;
  font-size: 14px;
  color: #6b7280;
  text-align: center;
}
.preview-image {
  display: block;
  max-width: 100%;
  margin: 0 auto;
}
.preview-frame {
  width: 100%;
  height: 100%;
  min-height: 70vh;
  background: #fff;
  border: 0;
}
.preview-markdown {
  padding: 20px 24px;
}
.preview-text {
  padding: 20px 24px;
  margin: 0;
  overflow-x: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #1f2937;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
