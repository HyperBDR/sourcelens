<template>
  <div>
    <section v-if="isDatasourceTask && summaryPanelVisible" class="mb-4">
      <h3 class="mb-4 text-sm font-semibold text-gray-900">
        {{ t('taskManagement.list.syncOverview') }}
      </h3>
      <div
        class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm"
      >
        <div class="border-b border-gray-200 bg-gray-50 px-4 py-3">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 class="text-sm font-semibold text-gray-900">
                {{ t('taskManagement.list.currentProgress') }}
              </h3>
              <p class="mt-1 text-xs text-gray-500">
                {{ progressDescription || '-' }}
              </p>
            </div>
            <span
              class="rounded-md border px-2.5 py-1 text-xs font-semibold"
              :class="progressStatusClass"
            >
              {{ progressStatusLabel }}
            </span>
          </div>
          <div class="mt-3">
            <div
              class="flex items-center justify-between text-xs text-gray-500"
            >
              <span>
                {{ progressLabel || t('taskManagement.list.scanTotalUnknown') }}
              </span>
              <span
                v-if="progressPercent !== null"
                class="rounded-md border border-blue-200 bg-blue-50 px-2 py-0.5 font-semibold text-blue-800"
              >
                {{ progressPercent }}%
              </span>
            </div>
            <div class="mt-1.5 h-2 overflow-hidden rounded-full bg-gray-100">
              <div
                v-if="progressPercent !== null"
                class="h-full rounded-full bg-blue-600 transition-all"
                :style="{ width: `${progressPercent}%` }"
              />
              <div
                v-else-if="isScanningProgress"
                class="h-full w-2/3 rounded-full bg-blue-500 animate-pulse"
              />
            </div>
          </div>
          <div class="mt-3 grid gap-2 sm:grid-cols-3">
            <div
              v-for="phase in datasourcePhases"
              :key="phase.key"
              class="rounded-md border px-3 py-2"
              :class="phase.class"
            >
              <div class="flex items-center justify-between gap-2">
                <span class="text-xs font-semibold">{{ phase.label }}</span>
                <StatusBadge :status="phase.status" />
              </div>
              <div class="mt-1 text-xs opacity-80">
                {{ phase.description }}
              </div>
            </div>
          </div>
        </div>

        <div class="space-y-4 p-4">
          <section v-if="syncStats.length" class="space-y-3">
            <div class="flex items-center justify-between gap-3">
              <h3 class="text-sm font-semibold text-gray-900">
                {{ t('taskManagement.list.syncSummary') }}
              </h3>
              <span class="text-xs text-gray-500">
                {{ t('taskManagement.list.files') }}:
                {{ syncSummary.files ?? syncSummary.documents ?? 0 }}
              </span>
            </div>
            <div class="space-y-3 rounded-md border border-gray-200 p-3">
              <div>
                <div class="mb-2 text-xs font-semibold uppercase text-gray-500">
                  {{ t('taskManagement.list.coreMetrics') }}
                </div>
                <div class="grid gap-2 sm:grid-cols-3">
                  <div
                    v-for="item in syncPrimaryStats"
                    :key="item.label"
                    class="min-h-14 rounded-md border px-3 py-2"
                    :class="statToneClass(item.tone)"
                    :title="statDetailsTitle(item.details)"
                  >
                    <div class="text-xs font-medium leading-4 opacity-75">
                      {{ item.label }}
                    </div>
                    <div class="mt-1 text-base font-semibold leading-5">
                      {{ item.value }}
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="syncSecondaryStats.length">
                <div class="mb-2 text-xs font-semibold uppercase text-gray-500">
                  {{ t('taskManagement.list.otherMetrics') }}
                </div>
                <div class="grid gap-2 sm:grid-cols-3">
                  <div
                    v-for="item in syncSecondaryStats"
                    :key="item.label"
                    class="min-h-12 rounded-md border border-gray-200 bg-gray-50 px-3 py-2"
                    :title="statDetailsTitle(item.details)"
                  >
                    <div class="text-xs leading-4 text-gray-500">
                      {{ item.label }}
                    </div>
                    <div class="mt-0.5 text-sm font-semibold text-gray-900">
                      {{ item.value }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section v-if="conversionSectionVisible" class="space-y-3">
            <div class="flex items-center justify-between gap-3">
              <h3 class="text-sm font-semibold text-gray-900">
                {{ t('taskManagement.list.conversionSummary') }}
              </h3>
              <span class="text-xs text-gray-500">
                {{ t('taskManagement.list.estimatedTokens') }}:
                {{ conversionTokenCount }}
              </span>
            </div>
            <div
              v-if="conversionNotice"
              class="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-600"
            >
              {{ conversionNotice }}
            </div>
            <div v-else class="space-y-3 rounded-md border border-gray-200 p-3">
              <div>
                <div class="mb-2 text-xs font-semibold uppercase text-gray-500">
                  {{ t('taskManagement.list.coreMetrics') }}
                </div>
                <div class="grid gap-2 sm:grid-cols-3">
                  <div
                    v-for="item in conversionPrimaryStats"
                    :key="item.label"
                    class="min-h-14 rounded-md border px-3 py-2"
                    :class="statToneClass(item.tone)"
                    :title="statDetailsTitle(item.details)"
                  >
                    <div class="text-xs font-medium leading-4 opacity-75">
                      {{ item.label }}
                    </div>
                    <div class="mt-1 text-base font-semibold leading-5">
                      {{ item.value }}
                    </div>
                  </div>
                </div>
              </div>
              <div v-if="conversionSecondaryStats.length">
                <div class="mb-2 text-xs font-semibold uppercase text-gray-500">
                  {{ t('taskManagement.list.modelAndCost') }}
                </div>
                <div class="grid gap-2 sm:grid-cols-3">
                  <div
                    v-for="item in conversionSecondaryStats"
                    :key="item.label"
                    class="min-h-12 rounded-md border border-gray-200 bg-gray-50 px-3 py-2"
                    :title="statDetailsTitle(item.details)"
                  >
                    <div class="text-xs leading-4 text-gray-500">
                      {{ item.label }}
                    </div>
                    <div class="mt-0.5 text-sm font-semibold text-gray-900">
                      {{ item.value }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>

        <div
          v-if="extensionStats.length || conversionWarnings.length"
          class="border-t border-gray-200 px-4 py-3"
        >
          <div v-if="extensionStats.length">
            <h3 class="mb-2 text-xs font-semibold uppercase text-gray-500">
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
                <span class="font-semibold text-gray-900">
                  {{ item.value }}
                </span>
              </span>
            </div>
          </div>
          <div
            v-if="conversionWarnings.length"
            class="mt-3 flex flex-wrap gap-2"
          >
            <span
              v-for="warning in conversionWarnings"
              :key="warning"
              class="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800"
            >
              {{ warning }}
            </span>
          </div>
        </div>
      </div>
    </section>

    <div v-if="isDatasourceTask && itemResults.length" class="mb-4">
      <button
        type="button"
        class="mb-4 flex w-full items-center justify-between gap-3 text-left"
        @click="changedItemsExpanded = !changedItemsExpanded"
      >
        <span class="flex items-center gap-2">
          <ChevronDown
            v-if="changedItemsExpanded"
            class="h-4 w-4 text-gray-500"
          />
          <ChevronRight v-else class="h-4 w-4 text-gray-500" />
          <span class="text-sm font-semibold text-gray-900">
            {{ t('taskManagement.list.changedItemDetails') }}
          </span>
        </span>
        <span class="text-xs text-gray-500">
          {{ itemResults.length }} {{ t('taskManagement.list.itemsUnit') }}
        </span>
      </button>
      <div
        v-if="changedItemsExpanded"
        class="overflow-hidden rounded-lg border border-gray-200"
      >
        <div class="max-h-72 overflow-auto">
          <table class="min-w-full divide-y divide-gray-200 text-sm">
            <thead class="sticky top-0 z-10 bg-gray-50 shadow-sm">
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
      </div>
    </div>

    <button
      type="button"
      class="mb-4 flex w-full items-center justify-between gap-3 text-left"
      @click="detailStepsExpanded = !detailStepsExpanded"
    >
      <span class="flex items-center gap-2">
        <ChevronDown v-if="detailStepsExpanded" class="h-4 w-4 text-gray-500" />
        <ChevronRight v-else class="h-4 w-4 text-gray-500" />
        <span class="text-sm font-semibold text-gray-900">
          {{ t('taskManagement.list.detailedSteps') }}
        </span>
      </span>
      <span class="text-xs text-gray-500">
        {{ detailSteps.length }} {{ t('taskManagement.list.itemsUnit') }}
      </span>
    </button>
    <div
      v-if="detailStepsExpanded && detailSteps.length > 0"
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
      v-else-if="detailStepsExpanded"
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
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { format } from 'date-fns'
import { ChevronDown, ChevronRight } from '@lucide/vue'

import StatusBadge from '@/components/ui/StatusBadge.vue'

const props = defineProps({
  task: { type: Object, default: null }
})

const { t } = useI18n()

const changedItemsExpanded = ref(false)
const detailStepsExpanded = ref(false)

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
  return `${current}/${total} ${t('taskManagement.list.itemsUnit')}`
})

const progressStatusKey = computed(() => {
  const status = String(props.task?.status || '').toUpperCase()
  if (['SUCCESS'].includes(status)) return 'completed'
  if (['FAILURE'].includes(status)) return 'failed'
  if (['REVOKED'].includes(status)) return 'cancelled'
  if (isTaskActive.value) return 'processing'
  return 'pending'
})

const progressStatusLabel = computed(() => {
  return t(`common.status.${progressStatusKey.value}`)
})

const progressStatusClass = computed(() => {
  const map = {
    completed: 'border-green-200 bg-green-50 text-green-800',
    failed: 'border-red-200 bg-red-50 text-red-800',
    cancelled: 'border-gray-200 bg-gray-100 text-gray-700',
    processing: 'border-blue-200 bg-blue-50 text-blue-800',
    pending: 'border-amber-200 bg-amber-50 text-amber-800'
  }
  return map[progressStatusKey.value] || map.pending
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

const summaryPanelVisible = computed(() => {
  return (
    syncStats.value.length > 0 ||
    conversionStats.value.length > 0 ||
    extensionStats.value.length > 0
  )
})

const datasourcePhases = computed(() => {
  const syncDone = Object.keys(syncSummary.value).length > 0
  const conversionDone = Object.keys(conversionSummary.value).length > 0
  return [
    {
      key: 'scan',
      label: t('taskManagement.list.scanningPhase'),
      description: `${t('taskManagement.list.scannedItems')} ${
        syncSummary.value.scanned ?? metadata.value.progress_current ?? 0
      }`,
      status: syncDone || isScanningProgress.value ? 'success' : 'pending',
      class:
        syncDone || isScanningProgress.value
          ? 'border-blue-200 bg-blue-50 text-blue-800'
          : 'border-gray-200 bg-white text-gray-600'
    },
    {
      key: 'sync',
      label: t('taskManagement.list.syncSummary'),
      description: `${t('taskManagement.list.changedItems')} ${
        syncSummary.value.changed ?? syncSummary.value.synced ?? 0
      } · ${t('taskManagement.list.skippedItems')} ${
        syncSummary.value.skipped ?? 0
      }`,
      status: isTaskActive.value
        ? 'processing'
        : syncDone
          ? 'success'
          : 'pending',
      class: isTaskActive.value
        ? 'border-blue-200 bg-blue-50 text-blue-800'
        : syncDone
          ? 'border-green-200 bg-green-50 text-green-800'
          : 'border-gray-200 bg-white text-gray-600'
    },
    {
      key: 'conversion',
      label: t('taskManagement.list.conversionSummary'),
      description: `${t('taskManagement.list.convertedItems')} ${
        conversionSummary.value.converted ?? 0
      } · ${t('taskManagement.list.conversionFailedItems')} ${
        conversionSummary.value.failed ?? 0
      }`,
      status: conversionDone
        ? conversionSummary.value.failed
          ? 'failed'
          : 'success'
        : isTaskActive.value
          ? 'processing'
          : 'pending',
      class: conversionDone
        ? conversionSummary.value.failed
          ? 'border-red-200 bg-red-50 text-red-800'
          : 'border-green-200 bg-green-50 text-green-800'
        : isTaskActive.value
          ? 'border-blue-200 bg-blue-50 text-blue-800'
          : 'border-gray-200 bg-white text-gray-600'
    }
  ]
})

const itemResults = computed(() => {
  if (!isDatasourceTask.value) return []
  if (syncChangedItems.value.length) {
    return syncChangedItems.value
  }
  return detailSteps.value.filter((step) =>
    ['item_done', 'item_failed'].includes(step.name || step.step)
  )
})

const syncChangedItems = computed(() => {
  const items = syncSummary.value.changed_items
  if (!Array.isArray(items)) return []
  return items.map((item) => ({
    status: item.status === 'synced' ? 'done' : item.status || 'done',
    item_name: item.name || item.path || '-',
    item_type: item.extension || item.source_type || '-',
    file: item.path || '',
    token: item.path || item.name || '',
    timestamp: item.timestamp || ''
  }))
})

const syncChangedItemDetails = computed(() => {
  return detailItemsFromArray(syncSummary.value.changed_items)
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
      key: 'scanned',
      label: t('taskManagement.list.scannedItems'),
      value: summary.scanned ?? totalItemEvents.value
    },
    {
      key: 'changed',
      label: t('taskManagement.list.changedItems'),
      value: summary.changed ?? summary.synced ?? done,
      details: syncChangedItemDetails.value
    },
    {
      key: 'skipped',
      label: t('taskManagement.list.skippedItems'),
      value: summary.skipped ?? skipped
    },
    {
      key: 'success',
      label: t('taskManagement.list.successItems'),
      value: successCount(summary, done)
    },
    {
      key: 'failed',
      label: t('taskManagement.list.failedItems'),
      value: summary.failed ?? failed
    },
    {
      key: 'deleted',
      label: t('taskManagement.list.deletedItems'),
      value: summary.deleted ?? 0
    },
    {
      key: 'folders',
      label: t('taskManagement.list.folders'),
      value: summary.folders ?? 0
    },
    {
      key: 'documents',
      label: t('taskManagement.list.documents'),
      value: summary.documents ?? 0
    },
    {
      key: 'files',
      label: t('taskManagement.list.files'),
      value: summary.files ?? done
    }
  ]
})

const syncPrimaryStats = computed(() => {
  return syncStats.value.slice(0, 6).map((item) => ({
    ...item,
    tone: statToneByLabel(item.label)
  }))
})

const syncSecondaryStats = computed(() => syncStats.value.slice(6))

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

const conversionItemDetails = computed(() => {
  return detailItemsFromArray(conversionSummary.value.items)
})

const conversionItemsByStatus = computed(() => {
  const groups = {
    converted: [],
    skipped: [],
    failed: []
  }
  conversionItemDetails.value.forEach((item) => {
    if (groups[item.status]) {
      groups[item.status].push(item)
    }
  })
  return groups
})

const conversionOptions = computed(() => {
  return (
    conversionSummary.value.options ||
    metadata.value.conversion ||
    metadata.value.sync_policy?.conversion ||
    props.task?.result?.conversion_summary?.options ||
    {}
  )
})

const conversionEnabled = computed(() => {
  if (typeof metadata.value.conversion_enabled === 'boolean') {
    return metadata.value.conversion_enabled
  }
  const options = conversionOptions.value
  return Boolean(
    options.document === true ||
      options.image === true ||
      options.embedded_image === true
  )
})

const conversionSectionVisible = computed(() => {
  return isDatasourceTask.value
})

const conversionNotice = computed(() => {
  if (!conversionEnabled.value) {
    return t('taskManagement.list.conversionDisabledNotice')
  }
  return ''
})

const conversionStats = computed(() => {
  if (!isDatasourceTask.value) return []
  const summary = conversionSummary.value
  const cost = summary.cost || {}
  return [
    {
      key: 'candidates',
      label: t('taskManagement.list.conversionCheckedItems'),
      value: summary.candidates ?? summary.total ?? summary.converted ?? 0,
      details: conversionItemDetails.value
    },
    {
      key: 'converted',
      label: t('taskManagement.list.convertedItems'),
      value: summary.converted ?? summary.total ?? 0,
      details: conversionItemsByStatus.value.converted
    },
    {
      key: 'success',
      label: t('taskManagement.list.conversionSuccessItems'),
      value: summary.success ?? summary.succeeded ?? summary.converted ?? 0,
      details: conversionItemsByStatus.value.converted
    },
    {
      key: 'failed',
      label: t('taskManagement.list.conversionFailedItems'),
      value: summary.failed ?? summary.errors ?? 0,
      details: conversionItemsByStatus.value.failed
    },
    {
      key: 'markdown',
      label: t('taskManagement.list.markdownItems'),
      value: summary.markdown ?? summary.markdown_files ?? 0,
      details: conversionItemsByStatus.value.converted
    },
    {
      key: 'skipped',
      label: t('taskManagement.list.conversionUnchangedSkippedItems'),
      value: summary.skipped ?? 0,
      details: conversionItemsByStatus.value.skipped
    },
    {
      key: 'xlsx',
      label: t('taskManagement.list.xlsxItems'),
      value: summary.xlsx_files ?? 0
    },
    {
      key: 'sheets',
      label: t('taskManagement.list.sheetItems'),
      value: summary.sheets ?? 0
    },
    {
      key: 'rows',
      label: t('taskManagement.list.rowItems'),
      value: summary.rows ?? 0
    },
    {
      key: 'model_calls',
      label: t('taskManagement.list.modelCalls'),
      value: cost.model_calls ?? 0
    },
    {
      key: 'estimated_tokens',
      label: t('taskManagement.list.estimatedTokens'),
      value: summary.estimated_tokens ?? cost.estimated_tokens ?? 0
    },
    {
      key: 'total_tokens',
      label: t('taskManagement.list.totalTokens'),
      value: cost.total_tokens ?? 0
    }
  ]
})

const conversionPrimaryStats = computed(() => {
  return conversionStats.value.slice(0, 6).map((item) => ({
    ...item,
    tone: statToneByLabel(item.label)
  }))
})

const conversionSecondaryStats = computed(() => conversionStats.value.slice(6))

const conversionWarnings = computed(() => {
  const warnings = conversionSummary.value.warnings
  return Array.isArray(warnings) ? warnings.filter(Boolean) : []
})

const conversionTokenCount = computed(() => {
  const summary = conversionSummary.value
  const cost = summary.cost || {}
  return summary.estimated_tokens ?? cost.estimated_tokens ?? 0
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

function statToneByLabel(label) {
  const failedLabels = [
    t('taskManagement.list.failedItems'),
    t('taskManagement.list.conversionFailedItems')
  ]
  const successLabels = [
    t('taskManagement.list.successItems'),
    t('taskManagement.list.conversionSuccessItems'),
    t('taskManagement.list.convertedItems')
  ]
  const warningLabels = [
    t('taskManagement.list.skippedItems'),
    t('taskManagement.list.deletedItems')
  ]
  if (failedLabels.includes(label)) return 'danger'
  if (successLabels.includes(label)) return 'success'
  if (warningLabels.includes(label)) return 'warning'
  return 'default'
}

function statToneClass(tone) {
  const map = {
    success: 'border-green-200 bg-green-50 text-green-900',
    danger: 'border-red-200 bg-red-50 text-red-900',
    warning: 'border-amber-200 bg-amber-50 text-amber-900',
    default: 'border-gray-200 bg-white text-gray-900'
  }
  return map[tone] || map.default
}

function detailItemsFromArray(items) {
  if (!Array.isArray(items)) return []
  return items
    .map((item) => ({
      status: item.status || '',
      path: item.path || item.file || '',
      name: item.name || item.path || item.file || '',
      reason: item.reason || '',
      extension: item.extension || extensionFromPath(item.path || item.file)
    }))
    .filter((item) => item.path || item.name)
}

function statDetailsTitle(details) {
  if (!Array.isArray(details) || details.length === 0) return ''
  const lines = details.slice(0, 20).map((item) => {
    const reason = item.reason ? ` (${item.reason})` : ''
    return `${item.path || item.name}${reason}`
  })
  if (details.length > lines.length) {
    lines.push(`... ${details.length - lines.length} more`)
  }
  return lines.join('\n')
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
