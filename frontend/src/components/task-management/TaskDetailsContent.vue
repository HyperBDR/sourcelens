<template>
  <div>
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

const itemResults = computed(() => {
  if (!isDatasourceTask.value) return []
  return detailSteps.value.filter((step) =>
    ['item_done', 'item_failed'].includes(step.name || step.step)
  )
})

const syncStats = computed(() => {
  if (!isDatasourceTask.value) return []
  const summary = metadata.value.sync_summary || {}
  const done = itemResults.value.filter((item) => item.status === 'done').length
  const failed = itemResults.value.filter(
    (item) => item.status === 'failed'
  ).length
  return [
    {
      label: t('taskManagement.list.successItems'),
      value: summary.documents ?? done
    },
    {
      label: t('taskManagement.list.failedItems'),
      value: summary.failed ?? failed
    },
    { label: t('taskManagement.list.folders'), value: summary.folders ?? 0 },
    { label: t('taskManagement.list.files'), value: summary.files ?? done }
  ]
})

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
    failed: 'failed'
  }
  return m[status] || status || 'pending'
}
</script>
