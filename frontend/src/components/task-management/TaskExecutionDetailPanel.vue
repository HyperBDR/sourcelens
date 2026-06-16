<template>
  <!-- Overlay -->
  <Transition
    enter-active-class="transition-opacity duration-200"
    enter-from-class="opacity-0"
    enter-to-class="opacity-100"
    leave-active-class="transition-opacity duration-150"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
  >
    <div
      v-if="show"
      @click="handleClose"
      class="fixed inset-0 bg-gray-900 bg-opacity-50 z-40"
    />
  </Transition>

  <!-- Right Panel -->
  <Transition
    enter-active-class="transition-transform duration-300 ease-out"
    enter-from-class="translate-x-full"
    enter-to-class="translate-x-0"
    leave-active-class="transition-transform duration-250 ease-in"
    leave-from-class="translate-x-0"
    leave-to-class="translate-x-full"
  >
    <div
      v-if="show"
      class="fixed inset-y-0 right-0 w-full max-w-2xl bg-white shadow-xl z-50 flex flex-col"
    >
      <!-- Header -->
      <div
        class="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-gray-50 to-gray-100 flex-shrink-0"
      >
        <h2 class="text-lg font-semibold text-gray-900">
          {{ t('taskManagement.list.details') }}
        </h2>
        <button
          @click="handleClose"
          class="p-1.5 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
        >
          <svg
            class="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      </div>

      <!-- Content - Scrollable -->
      <div class="flex-1 overflow-y-auto">
        <div v-if="task">
          <div
            class="sticky top-0 z-10 flex gap-5 border-b border-gray-200 bg-white px-6"
          >
            <button
              type="button"
              class="detail-tab"
              :class="activeDetailTab === 'basic' ? 'detail-tab-active' : ''"
              @click="activeDetailTab = 'basic'"
            >
              {{ t('taskManagement.list.basicInfo') }}
            </button>
            <button
              type="button"
              class="detail-tab"
              :class="
                activeDetailTab === 'details' ? 'detail-tab-active' : ''
              "
              @click="activeDetailTab = 'details'"
            >
              {{ t('taskManagement.list.taskDetails') }}
              <span
                v-if="isDatasourceTask && datasourceItemResults.length"
                class="ml-1 text-xs text-gray-400"
              >
                {{ datasourceItemResults.length }}
              </span>
            </button>
          </div>

          <div class="p-6 space-y-6">
            <!-- Basic Information -->
            <div v-show="activeDetailTab === 'basic'">
            <h3 class="text-sm font-semibold text-gray-900 mb-4">
              {{ t('taskManagement.list.basicInfo') }}
            </h3>
            <dl class="grid grid-cols-1 gap-4">
              <div>
                <dt
                  class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                >
                  {{ t('taskManagement.list.taskName') }}
                </dt>
                <dd class="text-sm font-medium text-gray-900">
                  {{ task.task_name || '-' }}
                </dd>
              </div>
              <div>
                <dt
                  class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                >
                  {{ t('taskManagement.list.module') }}
                </dt>
                <dd class="text-sm font-medium text-gray-900">
                  {{ task.module || '-' }}
                </dd>
              </div>
              <div>
                <dt
                  class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                >
                  {{ t('taskManagement.list.status') }}
                </dt>
                <dd>
                  <StatusBadge :status="mapTaskStatus(task.status)" />
                </dd>
              </div>
              <div>
                <dt
                  class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                >
                  {{ t('taskManagement.list.taskId') }}
                </dt>
                <dd class="text-sm font-medium text-gray-900 font-mono">
                  {{ task.task_id || '-' }}
                </dd>
              </div>
              <div>
                <dt
                  class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                >
                  {{ t('taskManagement.list.createdAt') }}
                </dt>
                <dd class="text-sm font-medium text-gray-900">
                  {{ formatDate(task.created_at) }}
                </dd>
              </div>
              <div>
                <dt
                  class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                >
                  {{ t('taskManagement.list.startedAt') }}
                </dt>
                <dd class="text-sm font-medium text-gray-900">
                  {{ formatDate(task.started_at) }}
                </dd>
              </div>
              <div>
                <dt
                  class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                >
                  {{ t('taskManagement.list.finishedAt') }}
                </dt>
                <dd class="text-sm font-medium text-gray-900">
                  {{ formatDate(task.finished_at) }}
                </dd>
              </div>
              <div>
                <dt
                  class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                >
                  {{ t('taskManagement.list.duration') }}
                </dt>
                <dd class="text-sm font-medium text-gray-900">
                  {{ formatDuration(task.duration) }}
                </dd>
              </div>
              <div>
                <dt
                  class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                >
                  {{ t('taskManagement.list.createdBy') }}
                </dt>
                <dd class="text-sm font-medium text-gray-900">
                  {{ task.created_by_username || '-' }}
                </dd>
              </div>
              <div v-if="task.error">
                <dt
                  class="text-xs font-semibold text-red-700 mb-2 uppercase tracking-wider"
                >
                  {{ t('taskManagement.list.error') }}
                </dt>
                <dd class="text-sm text-red-600 whitespace-pre-wrap">
                  {{ task.error }}
                </dd>
              </div>
              <div v-if="task.result !== undefined && task.result !== null">
                <dt
                  class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                >
                  {{ t('taskManagement.list.result') }}
                </dt>
                <dd class="text-sm text-gray-600">
                  <pre
                    class="bg-gray-50 p-3 rounded text-xs overflow-auto max-h-64"
                    >{{ JSON.stringify(task.result, null, 2) }}</pre
                  >
                </dd>
              </div>
            </dl>
            </div>

            <!-- Datasource task context -->
            <div
              v-if="isDatasourceTask"
              v-show="activeDetailTab === 'basic'"
              class="border-t border-gray-200 pt-6"
            >
            <h3 class="text-sm font-semibold text-gray-900 mb-4">
              {{ t('taskManagement.list.datasourceInfo') }}
            </h3>
            <dl class="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div
                v-for="item in datasourceDetailRows"
                :key="item.label"
                class="rounded-lg border border-gray-200 bg-gray-50 p-3"
              >
                <dt class="text-xs font-semibold text-gray-600 mb-1">
                  {{ item.label }}
                </dt>
                <dd
                  class="break-words text-sm text-gray-900"
                  :class="item.mono ? 'font-mono text-xs' : ''"
                >
                  {{ item.value }}
                </dd>
              </div>
            </dl>
            </div>

            <!-- Detailed steps / execution logs from metadata -->
            <div
              v-show="activeDetailTab === 'details'"
              class="border-t border-gray-200 pt-6"
            >
            <h3 class="text-sm font-semibold text-gray-900 mb-4">
              {{ t('taskManagement.list.detailedSteps') }}
            </h3>
            <div
              v-if="currentProgressText"
              class="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800"
            >
              <span class="font-medium"
                >{{ t('taskManagement.list.currentProgress') }}:</span
              >
              {{ currentProgressText }}
            </div>

            <div
              v-if="isDatasourceTask && datasourceSyncStats.length"
              class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4"
            >
              <div
                v-for="item in datasourceSyncStats"
                :key="item.label"
                class="rounded-lg border border-gray-200 bg-white p-3"
              >
                <div class="text-xs font-medium text-gray-500">
                  {{ item.label }}
                </div>
                <div class="mt-1 text-lg font-semibold text-gray-900">
                  {{ item.value }}
                </div>
              </div>
            </div>

            <div
              v-if="isDatasourceTask && datasourceItemResults.length"
              class="mb-4 overflow-hidden rounded-lg border border-gray-200"
            >
              <table class="min-w-full divide-y divide-gray-200 text-sm">
                <thead class="bg-gray-50">
                  <tr>
                    <th class="px-3 py-2 text-left font-semibold text-gray-600">
                      {{ t('taskManagement.list.itemName') }}
                    </th>
                    <th class="px-3 py-2 text-left font-semibold text-gray-600">
                      {{ t('taskManagement.list.status') }}
                    </th>
                    <th class="px-3 py-2 text-left font-semibold text-gray-600">
                      {{ t('taskManagement.list.resultFile') }}
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-gray-200 bg-white">
                  <tr
                    v-for="item in datasourceItemResults"
                    :key="`${item.token}-${item.status}-${item.timestamp}`"
                  >
                    <td class="px-3 py-2">
                      <div class="font-medium text-gray-900">
                        {{ item.item_name || item.token || '-' }}
                      </div>
                      <div class="font-mono text-xs text-gray-500">
                        {{ item.item_type || item.kind || '-' }}
                      </div>
                    </td>
                    <td class="px-3 py-2">
                      <StatusBadge :status="mapStepStatus(item.status)" />
                      <div
                        v-if="item.error"
                        class="mt-1 max-w-xs truncate text-xs text-red-700"
                        :title="item.error"
                      >
                        {{ item.error }}
                      </div>
                    </td>
                    <td class="px-3 py-2 font-mono text-xs text-gray-600">
                      {{ item.file || '-' }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div
              v-if="detailSteps.length > 0"
              class="rounded-lg border border-gray-200 bg-gray-50 shadow-sm overflow-hidden"
            >
              <div class="max-h-96 overflow-y-auto divide-y divide-gray-200">
                <div
                  v-for="(item, index) in detailSteps"
                  :key="index"
                  class="p-4 bg-white hover:bg-gray-50/80 transition-colors"
                  :class="
                    item.level === 'ERROR'
                      ? 'border-l-4 border-l-red-500'
                      : item.level === 'WARNING'
                        ? 'border-l-4 border-l-amber-500'
                        : ''
                  "
                >
                  <div class="flex items-start gap-3">
                    <span
                      class="flex-shrink-0 w-6 h-6 rounded-full bg-gray-200 text-gray-600 flex items-center justify-center text-xs font-semibold"
                    >
                      {{ index + 1 }}
                    </span>
                    <div class="flex-1 min-w-0">
                      <div class="flex flex-wrap items-center gap-2 mb-1">
                        <span
                          v-if="item.level"
                          class="inline-flex px-2 py-0.5 text-xs font-medium rounded"
                          :class="logLevelClass(item.level)"
                        >
                          {{ item.level }}
                        </span>
                        <span
                          v-if="item.step || item.name"
                          class="text-xs font-semibold text-gray-700"
                        >
                          {{ item.step || item.name }}
                        </span>
                        <span
                          v-if="item.timestamp"
                          class="text-xs text-gray-500"
                        >
                          {{ formatStepTime(item.timestamp) }}
                        </span>
                      </div>
                      <p
                        class="text-sm text-gray-800 whitespace-pre-wrap break-words"
                      >
                        {{ item.message }}
                      </p>
                      <pre
                        v-if="item.exception"
                        class="mt-2 text-xs font-mono text-red-700 whitespace-pre-wrap bg-red-50 p-2 rounded border border-red-100"
                        >{{ item.exception }}</pre
                      >
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <p
              v-else
              class="py-8 text-center text-sm text-gray-500 rounded-lg border border-gray-200 bg-gray-50"
            >
              {{ t('taskManagement.list.noStepsOrLogs') }}
            </p>
            </div>

            <!-- Traceback -->
            <div
              v-if="task.traceback"
              v-show="activeDetailTab === 'details'"
              class="border-t border-gray-200 pt-6"
            >
            <h3 class="text-sm font-semibold text-gray-900 mb-4">
              {{ t('taskManagement.list.traceback') }}
            </h3>
            <div
              class="bg-red-50 border border-red-200 rounded-lg p-4 shadow-sm"
            >
              <pre
                class="text-xs font-mono text-red-800 whitespace-pre-wrap overflow-auto max-h-96"
                >{{ task.traceback }}</pre
              >
            </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { format } from 'date-fns'
import { formatDuration } from '@/utils/formatting'
import StatusBadge from '@/components/ui/StatusBadge.vue'

const props = defineProps({
  show: {
    type: Boolean,
    default: false
  },
  task: {
    type: Object,
    default: null
  }
})

const emit = defineEmits(['close'])

const { t } = useI18n()
const activeDetailTab = ref('basic')

const metadata = computed(() => props.task?.metadata || {})

const detailSteps = computed(() => {
  const meta = metadata.value
  if (Array.isArray(meta.steps) && meta.steps.length > 0) {
    return meta.steps.map((s) => ({
      step: s.step ?? s.name,
      name: s.name ?? s.step,
      status: s.status,
      message: s.message ?? s.description ?? '',
      timestamp: s.timestamp ?? s.time,
      category: s.category,
      kind: s.kind,
      token: s.token,
      item_type: s.item_type,
      item_name: s.item_name,
      file: s.file,
      file_extension: s.file_extension,
      error: s.error,
      summary: s.summary
    }))
  }
  if (Array.isArray(meta.logs) && meta.logs.length > 0) {
    return meta.logs.map((log) => ({
      level: log.level,
      message: log.message ?? '',
      timestamp: log.timestamp,
      exception: log.exception
    }))
  }
  return []
})

const currentProgressText = computed(() => {
  const meta = metadata.value
  const percent = meta.progress_percent
  const msg = meta.progress_message
  const step = meta.progress_step
  if (percent != null && (msg || step)) {
    const parts = []
    if (step) parts.push(step)
    if (msg) parts.push(msg)
    if (percent != null) parts.push(`${percent}%`)
    return parts.join(' · ')
  }
  if (msg) return msg
  if (step) return step
  return ''
})

const isDatasourceTask = computed(() => {
  const meta = metadata.value
  return props.task?.module === 'lens_datasource' || meta.type === 'datasource'
})

const datasourceItemResults = computed(() => {
  if (!isDatasourceTask.value) return []
  return detailSteps.value.filter((step) =>
    ['item_done', 'item_failed'].includes(step.name || step.step)
  )
})

const datasourceSyncStats = computed(() => {
  if (!isDatasourceTask.value) return []
  const summary = metadata.value.sync_summary || {}
  const done = datasourceItemResults.value.filter(
    (item) => item.status === 'done'
  ).length
  const failed = datasourceItemResults.value.filter(
    (item) => item.status === 'failed'
  ).length
  const rows = [
    {
      label: t('taskManagement.list.successItems'),
      value: summary.documents ?? done
    },
    {
      label: t('taskManagement.list.failedItems'),
      value: summary.failed ?? failed
    },
    {
      label: t('taskManagement.list.folders'),
      value: summary.folders ?? 0
    },
    {
      label: t('taskManagement.list.files'),
      value: summary.files ?? done
    }
  ]
  return rows
})

const datasourceDetailRows = computed(() => {
  const meta = metadata.value
  const rows = [
    detailRow(t('taskManagement.list.datasourceName'), meta.datasource_name),
    detailRow(t('taskManagement.list.datasourceType'), formatSourceType(meta.source_type)),
    detailRow(t('taskManagement.list.lensnode'), meta.lensnode_name || meta.lensnode_uuid),
    detailRow(t('taskManagement.list.targetPath'), meta.target_path, true),
    detailRow(t('taskManagement.list.trigger'), meta.trigger),
    detailRow(
      t('taskManagement.list.syncInterval'),
      meta.sync_interval_seconds ? `${meta.sync_interval_seconds}s` : ''
    )
  ]
  if (meta.source_type === 'git') {
    rows.push(
      detailRow(t('taskManagement.list.repoUrl'), meta.repo_url, true),
      detailRow(t('taskManagement.list.branch'), meta.branch || 'main', true),
      detailRow(t('taskManagement.list.authScheme'), meta.auth_scheme),
      detailRow(
        t('taskManagement.list.credential'),
        meta.credential_configured
          ? t('common.status.enabled')
          : t('common.status.disabled')
      )
    )
  } else if (meta.source_type === 'feishu') {
    rows.push(
      detailRow(t('taskManagement.list.syncScope'), meta.sync_mode),
      detailRow(t('taskManagement.list.folderUrl'), meta.folder_url, true),
      detailRow(t('taskManagement.list.folderToken'), meta.folder_token, true),
      detailRow(t('taskManagement.list.documentUrl'), meta.document_url, true),
      detailRow(t('taskManagement.list.appToken'), meta.app_token, true),
      detailRow(t('taskManagement.list.docIds'), formatDocIds(meta.doc_ids), true),
      detailRow(t('taskManagement.list.recursive'), formatBool(meta.recursive)),
      detailRow(t('taskManagement.list.maxDepth'), meta.max_depth)
    )
  }
  return rows.filter((row) => row.value !== '-')
})

function detailRow(label, value, mono = false) {
  return {
    label,
    value: Array.isArray(value) ? value.join(', ') || '-' : value || '-',
    mono
  }
}

function formatSourceType(sourceType) {
  if (sourceType === 'git') return 'Git'
  if (sourceType === 'feishu') return 'Feishu'
  return sourceType || '-'
}

function formatDocIds(docIds) {
  if (Array.isArray(docIds)) return docIds.join(', ')
  return docIds || ''
}

function formatBool(value) {
  if (value === true) return t('common.yes')
  if (value === false) return t('common.no')
  return ''
}

function formatStepTime(value) {
  if (value == null) return ''
  try {
    const date =
      typeof value === 'number' ? new Date(value * 1000) : new Date(value)
    if (Number.isNaN(date.getTime())) return String(value)
    return format(date, 'yyyy-MM-dd HH:mm:ss')
  } catch {
    return String(value)
  }
}

function logLevelClass(level) {
  const map = {
    ERROR: 'bg-red-100 text-red-800',
    WARNING: 'bg-amber-100 text-amber-800',
    INFO: 'bg-blue-100 text-blue-800',
    DEBUG: 'bg-gray-100 text-gray-600',
    CRITICAL: 'bg-red-200 text-red-900'
  }
  return map[level] || 'bg-gray-100 text-gray-700'
}

const formatDate = (dateString) => {
  if (!dateString) return '-'
  try {
    return format(new Date(dateString), 'yyyy-MM-dd HH:mm:ss')
  } catch {
    return dateString
  }
}

const mapTaskStatus = (status) => {
  const m = {
    PENDING: 'pending',
    STARTED: 'processing',
    SUCCESS: 'success',
    FAILURE: 'failed',
    RETRY: 'processing',
    REVOKED: 'failed'
  }
  return m[status] || (status && status.toLowerCase()) || 'pending'
}

function mapStepStatus(status) {
  const m = {
    running: 'processing',
    done: 'success',
    failed: 'failed'
  }
  return m[status] || status || 'pending'
}

const handleClose = () => {
  emit('close')
}
</script>

<style scoped>
.detail-tab {
  @apply py-3 text-sm font-medium border-b-2 border-transparent text-gray-500 transition-colors;
}

.detail-tab:hover {
  @apply text-gray-700;
}

.detail-tab-active {
  @apply border-primary-500 text-primary-600;
}
</style>
