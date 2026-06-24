<template>
  <div>
    <div
      v-if="progressPanelVisible"
      class="mb-4 rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800"
    >
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="font-medium">{{ progressTitle }}</div>
          <div class="mt-1">
            {{ progressDescription }}
          </div>
        </div>
        <div
          v-if="progressPercent !== null"
          class="shrink-0 font-semibold text-blue-900"
        >
          {{ progressPercent }}%
        </div>
      </div>
      <div
        v-if="progressPercent !== null"
        class="mt-3 h-2 overflow-hidden rounded-full bg-blue-100"
      >
        <div
          class="h-full rounded-full bg-blue-600 transition-all"
          :style="{ width: `${progressPercent}%` }"
        />
      </div>
      <div
        v-else-if="isScanningProgress"
        class="mt-3 h-2 overflow-hidden rounded-full bg-blue-100"
      >
        <div class="h-full w-2/3 rounded-full bg-blue-500 animate-pulse" />
      </div>
      <div v-if="progressLabel" class="mt-1 text-xs font-medium text-blue-700">
        {{ progressLabel }}
      </div>
      <div
        v-if="isScanningProgress"
        class="mt-1 text-xs font-medium text-blue-700"
      >
        {{ t('taskManagement.list.scanTotalUnknown') }}
      </div>
      <div
        v-if="isScanningProgress && scanningStats.length"
        class="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4"
      >
        <div
          v-for="item in scanningStats"
          :key="item.label"
          class="rounded border border-blue-100 bg-white/70 px-2.5 py-2"
        >
          <div class="text-xs text-blue-700">{{ item.label }}</div>
          <div class="mt-0.5 font-semibold text-blue-950">
            {{ item.value }}
          </div>
        </div>
      </div>
    </div>

    <h3
      v-if="isDatasourceTask && syncStats.length"
      class="mb-3 text-sm font-semibold text-gray-900"
    >
      {{ t('taskManagement.list.syncSummary') }}
    </h3>
    <div
      v-if="isDatasourceTask && syncStats.length"
      class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4"
    >
      <div
        v-for="item in syncStats"
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

    <h3
      v-if="isDatasourceTask && conversionStats.length"
      class="mb-3 text-sm font-semibold text-gray-900"
    >
      {{ t('taskManagement.list.conversionSummary') }}
    </h3>
    <div
      v-if="isDatasourceTask && conversionStats.length"
      class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4"
    >
      <div
        v-for="item in conversionStats"
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
      v-if="isDatasourceTask && extensionStats.length"
      class="mb-4 rounded-lg border border-gray-200 bg-white p-4"
    >
      <h3 class="mb-3 text-sm font-semibold text-gray-900">
        {{ t('taskManagement.list.fileTypeStats') }}
      </h3>
      <div class="flex flex-wrap gap-2">
        <span
          v-for="item in extensionStats"
          :key="item.label"
          class="inline-flex items-center gap-2 rounded border border-gray-200 bg-gray-50 px-2.5 py-1 text-sm text-gray-700"
        >
          <span class="font-mono text-xs uppercase text-gray-500">
            {{ item.label }}
          </span>
          <span class="font-semibold text-gray-900">{{ item.value }}</span>
        </span>
      </div>
    </div>

    <div
      v-if="isDatasourceTask && itemResults.length"
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
            v-for="item in itemResults"
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

    <h3 class="text-sm font-semibold text-gray-900 mb-4">
      {{ t('taskManagement.list.detailedSteps') }}
    </h3>
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
                <span v-if="item.timestamp" class="text-xs text-gray-500">
                  {{ formatStepTime(item.timestamp) }}
                </span>
              </div>
              <p class="text-sm text-gray-800 whitespace-pre-wrap break-words">
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

    <div v-if="task?.traceback" class="border-t border-gray-200 pt-6 mt-6">
      <h3 class="text-sm font-semibold text-gray-900 mb-4">
        {{ t('taskManagement.list.traceback') }}
      </h3>
      <div class="bg-red-50 border border-red-200 rounded-lg p-4 shadow-sm">
        <pre
          class="text-xs font-mono text-red-800 whitespace-pre-wrap overflow-auto max-h-96"
          >{{ task.traceback }}</pre
        >
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { format } from 'date-fns'

import StatusBadge from '@/components/ui/StatusBadge.vue'

const props = defineProps({
  task: { type: Object, default: null }
})

const { t } = useI18n()

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

const latestStep = computed(() => {
  if (!detailSteps.value.length) return null
  return detailSteps.value[detailSteps.value.length - 1]
})

const latestStepSummary = computed(() => {
  return latestStep.value?.summary || {}
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

const progressPercent = computed(() => {
  const meta = metadata.value
  const percent = meta.progress_percent
  if (percent == null) return null
  const value = Number(percent)
  if (!Number.isFinite(value)) return null
  return Math.max(0, Math.min(100, value))
})

const progressPanelVisible = computed(() => {
  return (
    Boolean(currentProgressText.value) ||
    progressPercent.value !== null ||
    isScanningProgress.value
  )
})

const progressTitle = computed(() => {
  if (isScanningProgress.value) {
    return t('taskManagement.list.scanningPhase')
  }
  if (progressPercent.value !== null) {
    return t('taskManagement.list.syncingPhase')
  }
  return t('taskManagement.list.currentProgress')
})

const progressDescription = computed(() => {
  if (isScanningProgress.value) {
    const summary = syncSummary.value
    return t('taskManagement.list.scanningDescription', {
      scanned: summary.scanned ?? metadata.value.progress_current ?? 0,
      folders: summary.folders ?? 0,
      skipped: summary.skipped ?? 0
    })
  }
  return currentProgressText.value || progressLabel.value
})

const progressLabel = computed(() => {
  const meta = metadata.value
  const current = meta.progress_current
  const total = meta.progress_total
  if (current == null || total == null) return ''
  return `${current}/${total} · ${progressPercent.value ?? 0}%`
})

const isDatasourceTask = computed(() => {
  const meta = metadata.value
  return props.task?.module === 'lens_datasource' || meta.type === 'datasource'
})

const isTaskActive = computed(() => {
  const status = String(props.task?.status || '').toUpperCase()
  return ['PENDING', 'RECEIVED', 'STARTED', 'RETRY'].includes(status)
})

const isScanningProgress = computed(() => {
  if (!isDatasourceTask.value || !isTaskActive.value) return false
  if (progressPercent.value !== null || metadata.value.progress_total != null) {
    return false
  }
  const stepName = latestStep.value?.name || latestStep.value?.step
  const summary = syncSummary.value
  return (
    ['scan_folder', 'scan_progress'].includes(stepName) ||
    summary.scanned != null
  )
})

const scanningStats = computed(() => {
  if (!isScanningProgress.value) return []
  const summary = syncSummary.value
  return [
    {
      label: t('taskManagement.list.scannedItems'),
      value: summary.scanned ?? metadata.value.progress_current ?? 0
    },
    { label: t('taskManagement.list.folders'), value: summary.folders ?? 0 },
    {
      label: t('taskManagement.list.skippedItems'),
      value: summary.skipped ?? 0
    }
  ]
})

const itemResults = computed(() => {
  if (!isDatasourceTask.value) return []
  return detailSteps.value.filter((step) =>
    ['item_done', 'item_failed', 'item_skipped'].includes(
      step.name || step.step
    )
  )
})

const syncStats = computed(() => {
  if (!isDatasourceTask.value) return []
  const summary = syncSummary.value
  const done = itemResults.value.filter((item) => item.status === 'done').length
  const failed = itemResults.value.filter(
    (item) => item.status === 'failed'
  ).length
  const skipped = itemResults.value.filter(
    (item) => item.name === 'item_skipped' || item.step === 'item_skipped'
  ).length
  return [
    {
      label: t('taskManagement.list.scannedItems'),
      value: summary.scanned ?? totalItemEvents.value
    },
    {
      label: t('taskManagement.list.changedItems'),
      value: summary.changed ?? summary.synced ?? done
    },
    {
      label: t('taskManagement.list.skippedItems'),
      value: summary.skipped ?? skipped
    },
    {
      label: t('taskManagement.list.successItems'),
      value: successCount(summary, done)
    },
    {
      label: t('taskManagement.list.failedItems'),
      value: summary.failed ?? failed
    },
    {
      label: t('taskManagement.list.deletedItems'),
      value: summary.deleted ?? 0
    },
    { label: t('taskManagement.list.folders'), value: summary.folders ?? 0 },
    {
      label: t('taskManagement.list.documents'),
      value: summary.documents ?? 0
    },
    { label: t('taskManagement.list.files'), value: summary.files ?? done }
  ]
})

const syncSummary = computed(() => {
  return (
    metadata.value.sync_summary ||
    latestStepSummary.value ||
    props.task?.result ||
    {}
  )
})

const conversionSummary = computed(() => {
  return (
    metadata.value.conversion_summary ||
    metadata.value.markdown_summary ||
    props.task?.result?.conversion_summary ||
    {}
  )
})

const conversionStats = computed(() => {
  if (!isDatasourceTask.value) return []
  const summary = conversionSummary.value
  if (!Object.keys(summary).length) return []
  return [
    {
      label: t('taskManagement.list.convertedItems'),
      value: summary.converted ?? summary.total ?? 0
    },
    {
      label: t('taskManagement.list.conversionSuccessItems'),
      value: summary.success ?? summary.succeeded ?? summary.converted ?? 0
    },
    {
      label: t('taskManagement.list.conversionFailedItems'),
      value: summary.failed ?? summary.errors ?? 0
    },
    {
      label: t('taskManagement.list.markdownItems'),
      value: summary.markdown ?? summary.markdown_files ?? 0
    }
  ]
})

const totalItemEvents = computed(() => {
  return detailSteps.value.filter((step) =>
    ['item_done', 'item_failed', 'item_skipped', 'item_started'].includes(
      step.name || step.step
    )
  ).length
})

const extensionStats = computed(() => {
  if (!isDatasourceTask.value) return []
  const fromSummary = syncSummary.value.by_extension || {}
  const counts = { ...fromSummary }
  if (!Object.keys(counts).length) {
    itemResults.value.forEach((item) => {
      const extension = normalizeExtension(
        item.file_extension || extensionFromPath(item.file)
      )
      counts[extension] = Number(counts[extension] || 0) + 1
    })
  }
  return Object.entries(counts)
    .map(([label, value]) => ({
      label: normalizeExtension(label),
      value: Number(value) || 0
    }))
    .filter((item) => item.value > 0)
    .sort((a, b) => b.value - a.value || a.label.localeCompare(b.label))
})

function successCount(summary, fallbackDone) {
  if (summary.success != null) return summary.success
  if (
    summary.documents != null ||
    summary.files != null ||
    summary.skipped != null
  ) {
    return (
      Number(summary.documents || 0) +
      Number(summary.files || 0) +
      Number(summary.skipped || 0)
    )
  }
  if (summary.synced != null) return summary.synced
  return fallbackDone
}

function extensionFromPath(path) {
  const match = String(path || '').match(/\.([^.\\/]+)$/)
  return match ? match[1] : ''
}

function normalizeExtension(value) {
  return String(value || 'unknown')
    .replace(/^\./, '')
    .toLowerCase()
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

function mapStepStatus(status) {
  const m = {
    running: 'processing',
    done: 'success',
    failed: 'failed',
    skipped: 'cancelled'
  }
  return m[status] || status || 'pending'
}
</script>
