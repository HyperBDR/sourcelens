<script setup>
import { nextTick, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Download, Maximize2, Minimize2, X } from '@lucide/vue'

import MarkdownRenderer from '@/components/ui/MarkdownRenderer.vue'
import { fetchDeliverableBlob, previewKind } from '@/utils/filePreview'
import { escapeHtml, sanitizeHtml } from '@/utils/sanitize'

const props = defineProps({
  // The delivered file to preview, or null when the modal is closed.
  file: { type: Object, default: null }
})

const emit = defineEmits(['close', 'download'])

const { t } = useI18n()

const kind = ref('')
const objectUrl = ref('')
const textContent = ref('')
const docxContent = ref('')
const workbook = ref(null)
const sheetNames = ref([])
const selectedSheet = ref('')
const pptxHost = ref(null)
const previewPanel = ref(null)
const isFullscreen = ref(false)
const loading = ref(false)
const failed = ref(false)
let currentUrl = ''
let loadSeq = 0
let pptxPreviewer = null

function renderSheet(name) {
  if (!workbook.value || !name) return ''
  const XLSX = workbook.value.XLSX
  const rows = XLSX.utils.sheet_to_json(workbook.value.sheetMap[name], {
    header: 1,
    defval: '',
    raw: false
  })
  return `<table class="preview-spreadsheet-table"><tbody>${rows
    .map(
      (row) =>
        `<tr>${row
          .map((cell) => `<td>${escapeHtml(String(cell))}</td>`)
          .join('')}</tr>`
    )
    .join('')}</tbody></table>`
}

function updateSheet(name) {
  selectedSheet.value = name
}

function cleanup() {
  if (currentUrl) {
    URL.revokeObjectURL(currentUrl)
    currentUrl = ''
  }
  objectUrl.value = ''
  textContent.value = ''
  docxContent.value = ''
  workbook.value = null
  sheetNames.value = []
  selectedSheet.value = ''
  if (pptxPreviewer) {
    pptxPreviewer.destroy()
    pptxPreviewer = null
  }
  if (pptxHost.value) {
    pptxHost.value.innerHTML = ''
  }
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
    if (kind.value === 'pptx') {
      const { init: initPptxPreview } = await import('pptx-preview')
      const buffer = await blob.arrayBuffer()
      await nextTick()
      if (seq !== loadSeq || !pptxHost.value) {
        return
      }
      pptxPreviewer = initPptxPreview(pptxHost.value, {
        width: 900,
        height: 620,
        mode: 'list'
      })
      await pptxPreviewer.preview(buffer)
    } else if (kind.value === 'docx') {
      const { default: mammoth } = await import('mammoth')
      const result = await mammoth.convertToHtml({
        arrayBuffer: await blob.arrayBuffer()
      })
      if (seq !== loadSeq) return
      docxContent.value = sanitizeHtml(result.value)
    } else if (kind.value === 'xlsx') {
      const XLSX = await import('xlsx')
      const parsed = XLSX.read(await blob.arrayBuffer(), {
        type: 'array',
        cellText: true,
        cellDates: true
      })
      if (seq !== loadSeq) return
      const names = parsed.SheetNames || []
      workbook.value = {
        XLSX,
        sheetMap: parsed.Sheets
      }
      sheetNames.value = names
      selectedSheet.value = names[0] || ''
    } else if (kind.value === 'text' || kind.value === 'markdown') {
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
  exitFullscreen()
  emit('close')
}

async function enterFullscreen() {
  isFullscreen.value = true
  if (previewPanel.value?.requestFullscreen) {
    try {
      await previewPanel.value.requestFullscreen()
    } catch {
      // Keep the CSS fallback when the browser denies fullscreen access.
    }
  }
}

function exitFullscreen() {
  if (document.fullscreenElement && document.exitFullscreen) {
    document.exitFullscreen().catch(() => {})
  }
  isFullscreen.value = false
}

function toggleFullscreen() {
  if (isFullscreen.value) {
    exitFullscreen()
  } else {
    enterFullscreen()
  }
}

function onFullscreenChange() {
  isFullscreen.value = Boolean(document.fullscreenElement)
}

function onDownload() {
  if (props.file) {
    emit('download', props.file)
  }
}

function onKeydown(event) {
  if (event.key === 'Escape') {
    if (isFullscreen.value) {
      exitFullscreen()
      return
    }
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
      document.addEventListener('fullscreenchange', onFullscreenChange)
      lockScroll()
    } else {
      document.removeEventListener('keydown', onKeydown)
      document.removeEventListener('fullscreenchange', onFullscreenChange)
      exitFullscreen()
      unlockScroll()
    }
  },
  { immediate: true }
)

onUnmounted(() => {
  cleanup()
  document.removeEventListener('keydown', onKeydown)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  exitFullscreen()
  unlockScroll()
})
</script>

<template>
  <Teleport to="body">
    <div v-if="file" class="preview-backdrop" @click="close">
      <div
        ref="previewPanel"
        class="preview-panel"
        :class="{ 'preview-panel--fullscreen': isFullscreen }"
        @click.stop
      >
        <header class="preview-header">
          <span class="preview-title" :title="file.filename">
            {{ file.filename }}
          </span>
          <div class="preview-tools">
            <button
              type="button"
              class="preview-tool"
              :title="
                t(
                  isFullscreen
                    ? 'lens.chat.exitFullscreen'
                    : 'lens.chat.enterFullscreen'
                )
              "
              :aria-label="
                t(
                  isFullscreen
                    ? 'lens.chat.exitFullscreen'
                    : 'lens.chat.enterFullscreen'
                )
              "
              @click="toggleFullscreen"
            >
              <Minimize2 v-if="isFullscreen" :size="18" />
              <Maximize2 v-else :size="18" />
            </button>
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

          <div
            v-else-if="kind === 'pptx'"
            ref="pptxHost"
            class="preview-pptx"
          ></div>

          <article
            v-else-if="kind === 'docx'"
            class="preview-docx"
            v-html="docxContent"
          ></article>

          <div v-else-if="kind === 'xlsx'" class="preview-xlsx">
            <div class="preview-sheet-tabs" role="tablist">
              <button
                v-for="name in sheetNames"
                :key="name"
                type="button"
                class="preview-sheet-tab"
                :class="{ 'preview-sheet-tab--active': name === selectedSheet }"
                role="tab"
                :aria-selected="name === selectedSheet"
                @click="updateSheet(name)"
              >
                {{ name }}
              </button>
            </div>
            <div
              class="preview-sheet-content"
              v-html="renderSheet(selectedSheet)"
            ></div>
          </div>

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
  background: var(--sl-bg-surface);
  border-radius: 12px;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.4);
}
.preview-panel--fullscreen,
.preview-panel:fullscreen {
  width: 100vw;
  max-width: none;
  height: 100vh;
  max-height: none;
  border-radius: 0;
}
.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--sl-border-default);
}
.preview-title {
  min-width: 0;
  overflow: hidden;
  font-size: 14px;
  font-weight: 600;
  color: var(--sl-text-primary);
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
  color: var(--sl-text-muted);
  border-radius: 8px;
  transition: all 0.15s;
}
.preview-tool:hover {
  color: var(--sl-accent);
  background: var(--sl-bg-hover);
}
.preview-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--sl-bg-canvas);
}
.preview-status {
  padding: 48px 16px;
  font-size: 14px;
  color: var(--sl-text-muted);
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
  background: var(--sl-bg-surface);
  border: 0;
}
.preview-pptx {
  min-height: 620px;
  overflow: auto;
  background: #202124;
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
  color: var(--sl-text-primary);
  white-space: pre-wrap;
  word-break: break-word;
}
.preview-docx {
  max-width: 860px;
  min-height: 100%;
  padding: 32px 40px;
  margin: 0 auto;
  color: var(--sl-text-primary);
  background: var(--sl-bg-surface);
}
.preview-docx :deep(img) {
  max-width: 100%;
}
.preview-xlsx {
  min-width: max-content;
  min-height: 100%;
  padding: 12px;
}
.preview-sheet-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
}
.preview-sheet-tab {
  padding: 7px 12px;
  color: var(--sl-text-muted);
  border-radius: 6px;
}
.preview-sheet-tab--active,
.preview-sheet-tab:hover {
  color: var(--sl-text-primary);
  background: var(--sl-bg-surface);
}
.preview-sheet-content {
  overflow: auto;
  background: var(--sl-bg-surface);
}
.preview-sheet-content :deep(table) {
  border-collapse: collapse;
}
.preview-sheet-content :deep(td) {
  min-width: 96px;
  max-width: 360px;
  padding: 7px 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border: 1px solid var(--sl-border-default);
}
</style>
