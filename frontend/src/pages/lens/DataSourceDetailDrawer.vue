<template>
  <BaseDrawer
    :show="show"
    :title="t('lensAdmin.datasourceDetail.title')"
    :subtitle="datasource?.name || ''"
    width="2xl"
    @close="$emit('close')"
  >
    <div v-if="datasource">
      <div
        class="sticky top-0 z-10 -mx-6 flex gap-5 border-b border-line bg-surface px-6"
      >
        <button
          type="button"
          class="detail-tab"
          :class="activeTab === 'basic' ? 'detail-tab-active' : ''"
          @click="activeTab = 'basic'"
        >
          {{ t('lensAdmin.datasourceDetail.tabs.basic') }}
        </button>
        <button
          type="button"
          class="detail-tab"
          :class="activeTab === 'details' ? 'detail-tab-active' : ''"
          @click="activeTab = 'details'"
        >
          {{ t('lensAdmin.datasourceDetail.tabs.details') }}
        </button>
      </div>

      <div v-show="activeTab === 'basic'" class="space-y-6 pt-6">
        <section>
          <h3 class="mb-4 text-sm font-semibold text-ink-900">
            {{ t('lensAdmin.datasourceDetail.basicInfo') }}
          </h3>
          <dl class="grid grid-cols-1 gap-4">
            <div>
              <dt
                class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600"
              >
                {{ t('lensAdmin.fields.name') }}
              </dt>
              <dd class="break-words text-sm font-medium text-ink-900">
                {{ datasource.name || emptyValue }}
              </dd>
            </div>
            <div>
              <dt
                class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600"
              >
                UUID
              </dt>
              <dd
                class="break-words font-mono text-xs font-medium text-ink-900"
              >
                {{ datasource.uuid }}
              </dd>
            </div>
            <div>
              <dt
                class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600"
              >
                {{ t('lensAdmin.fields.status') }}
              </dt>
              <dd>
                <StatusBadge :status="datasource.status" />
              </dd>
            </div>
          </dl>
        </section>

        <section class="border-t border-line pt-6">
          <h3 class="mb-4 text-sm font-semibold text-ink-900">
            {{ t('lensAdmin.datasourceDetail.connection') }}
          </h3>
          <dl class="grid grid-cols-1 gap-4">
            <div v-for="item in datasourceConnectionDetails" :key="item.label">
              <dt
                class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600"
              >
                {{ item.label }}
              </dt>
              <dd
                class="break-words text-sm font-medium text-ink-900"
                :class="item.mono ? 'font-mono text-xs' : ''"
              >
                {{ item.value }}
              </dd>
            </div>
          </dl>
        </section>

        <section class="border-t border-line pt-6">
          <h3 class="mb-4 text-sm font-semibold text-ink-900">
            {{ t('lensAdmin.datasourceDetail.sync') }}
          </h3>
          <dl class="grid grid-cols-1 gap-4">
            <div v-for="item in datasourceSyncDetails" :key="item.label">
              <dt
                class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600"
              >
                {{ item.label }}
              </dt>
              <dd
                class="break-words text-sm font-medium text-ink-900"
                :class="item.mono ? 'font-mono text-xs' : ''"
              >
                {{ item.value }}
              </dd>
            </div>
          </dl>
        </section>
      </div>
      <div v-show="activeTab === 'details'" class="pt-6">
        <div
          class="relative overflow-hidden rounded-lg border border-line bg-surface shadow-sm"
        >
          <ul class="divide-y divide-line bg-surface">
            <li
              class="grid grid-cols-[1fr_140px_100px_100px_80px_24px] items-center gap-3 bg-surface-sunken px-4 py-2 text-center text-xs font-semibold uppercase tracking-wider text-ink-600"
            >
              <span>{{
                t('lensAdmin.datasourceDetail.details.colTaskName')
              }}</span>
              <span>{{
                t('lensAdmin.datasourceDetail.details.colStartedAt')
              }}</span>
              <span>{{
                t('lensAdmin.datasourceDetail.details.colStatus')
              }}</span>
              <span>{{
                t('lensAdmin.datasourceDetail.details.colTrigger')
              }}</span>
              <span>{{
                t('lensAdmin.datasourceDetail.details.colDuration')
              }}</span>
              <span></span>
            </li>
            <li
              v-if="tasksLoading"
              class="px-4 py-6 text-center text-sm text-ink-500"
            >
              {{ t('common.loading') }}
            </li>
            <li
              v-else-if="!tasks.length"
              class="px-4 py-6 text-center text-sm text-ink-500"
            >
              {{ t('common.noData') }}
            </li>
            <template v-else>
              <li
                v-for="task in tasks"
                :key="task.id"
                class="border-l-2 transition-colors duration-150"
                :class="
                  expandedTaskId === task.id
                    ? 'border-primary-500 bg-primary-50'
                    : 'border-transparent hover:bg-surface-sunken'
                "
              >
                <div
                  class="grid grid-cols-[1fr_140px_100px_100px_80px_24px] items-center gap-3 px-4 py-2 text-center text-sm"
                  :class="
                    tasksLoading
                      ? 'cursor-not-allowed opacity-60'
                      : 'cursor-pointer'
                  "
                  @click="toggleTaskExpand(task)"
                >
                  <span
                    class="truncate text-left text-sm font-medium text-ink-900"
                    :title="task.task_name"
                  >
                    {{ task.task_name || '-' }}
                  </span>
                  <span
                    class="whitespace-nowrap text-sm font-medium text-ink-900"
                  >
                    {{ formatDate(task.started_at) }}
                  </span>
                  <div class="flex justify-center">
                    <StatusBadge :status="mapTaskStatus(task.status)" />
                  </div>
                  <span class="whitespace-nowrap text-sm text-ink-500">
                    {{ formatTrigger(task) }}
                  </span>
                  <span class="whitespace-nowrap text-sm text-ink-500">
                    {{ formatDuration(task.duration) }}
                  </span>
                  <span
                    class="text-center text-ink-400 transition-transform duration-150"
                    :class="expandedTaskId === task.id ? 'rotate-90' : ''"
                    >▸</span
                  >
                </div>
                <div
                  v-if="expandedTaskId === task.id"
                  class="border-t border-line bg-surface-sunken px-4 py-3"
                >
                  <div
                    v-if="expandedTaskDetailLoading"
                    class="py-2 text-center text-xs text-ink-500"
                  >
                    {{ t('common.loading') }}
                  </div>
                  <TaskSummaryCard v-else :task="expandedTask" />
                </div>
              </li>
            </template>
          </ul>
        </div>

        <div
          v-if="totalCount > 0"
          class="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4"
        >
          <p class="text-sm text-ink-500">
            {{ t('common.pagination.showing', paginationShowing) }}
          </p>
          <div class="flex items-center gap-2">
            <BaseButton
              variant="outline"
              size="sm"
              :disabled="tasksLoading || currentPage <= 1"
              @click="goPrevPage"
            >
              {{ t('common.pagination.previous') }}
            </BaseButton>
            <BaseButton
              variant="outline"
              size="sm"
              :disabled="tasksLoading || currentPage >= totalPages"
              @click="goNextPage"
            >
              {{ t('common.pagination.next') }}
            </BaseButton>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="py-12 text-center text-sm text-ink-500">
      {{ t('lensAdmin.datasourceDetail.selectHint') }}
    </div>
  </BaseDrawer>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { format } from 'date-fns'

import api from '@/api'
import { taskManagementApi } from '@/admin/api/taskManagement'
import { extractErrorMessage, extractResponseData } from '@/utils/api'
import { formatDuration } from '@/utils/formatting'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import TaskSummaryCard from '@/components/task-management/TaskSummaryCard.vue'

import { EMPTY_VALUE as emptyValue } from './adminHelpers'
import { formatDocIds } from './datasourceHelpers'
import { useShortDateTime } from './useShortDateTime'

const props = defineProps({
  show: { type: Boolean, default: false },
  datasource: { type: Object, default: null },
  lensnodes: { type: Array, default: () => [] }
})

defineEmits(['close'])

const { t } = useI18n()
const formatDateTime = useShortDateTime()
const activeTab = ref('basic')

const tasks = ref([])
const tasksLoading = ref(false)
const currentPage = ref(1)
const totalCount = ref(0)
const totalPages = ref(1)
const pageSize = 10
const processingRefreshTimer = ref(null)
const processingRefreshInFlight = ref(false)
const taskRequestSeq = ref(0)

const expandedTaskId = ref(null)
const expandedTask = ref(null)
const expandedTaskDetailLoading = ref(false)

const PROCESSING_STATUSES = new Set(['PENDING', 'STARTED', 'RETRY'])

const paginationShowing = computed(() => ({
  from: (currentPage.value - 1) * pageSize + 1,
  to: Math.min(currentPage.value * pageSize, totalCount.value),
  total: totalCount.value
}))

function mapTaskStatus(status) {
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

function isProcessingStatus(status) {
  return PROCESSING_STATUSES.has(String(status || '').toUpperCase())
}

function formatDate(val) {
  if (!val) return '-'
  try {
    return format(new Date(val), 'yyyy-MM-dd HH:mm')
  } catch {
    return val
  }
}

async function loadTasks() {
  const requestSeq = taskRequestSeq.value + 1
  taskRequestSeq.value = requestSeq
  const uuid = props.datasource?.uuid
  if (!uuid) {
    tasks.value = []
    totalCount.value = 0
    totalPages.value = 1
    return
  }
  tasksLoading.value = true
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize
    }
    const res = await api.get(
      `/lens/admin/datasources/${uuid}/sync-tasks/`,
      { params }
    )
    const data = extractResponseData(res)
    const list =
      data?.results ?? data?.list ?? (Array.isArray(data) ? data : [])
    const serverTotal = data?.count ?? data?.pagination?.total
    const total = Number.isFinite(Number(serverTotal))
      ? Number(serverTotal)
      : list.length
    if (requestSeq !== taskRequestSeq.value) {
      return
    }
    tasks.value = list
    totalCount.value = total
    totalPages.value = total > 0 ? Math.ceil(total / pageSize) : 1
  } catch (e) {
    if (requestSeq !== taskRequestSeq.value) {
      return
    }
    tasks.value = []
    totalCount.value = 0
    totalPages.value = 1
    // eslint-disable-next-line no-console
    console.error(extractErrorMessage(e, t('common.error')))
  } finally {
    if (requestSeq === taskRequestSeq.value) {
      tasksLoading.value = false
    }
  }
}

async function refreshProcessingTasks() {
  if (processingRefreshInFlight.value) return
  const processingTasks = tasks.value.filter((task) =>
    isProcessingStatus(task.status)
  )
  if (!processingTasks.length) return
  processingRefreshInFlight.value = true
  try {
    const results = await Promise.allSettled(
      processingTasks.map((task) => taskManagementApi.getExecution(task.id))
    )
    const refreshedById = new Map()
    results.forEach((result) => {
      if (result.status !== 'fulfilled') return
      const row = extractResponseData(result.value)
      if (row?.id == null) return
      refreshedById.set(String(row.id), row)
    })
    if (!refreshedById.size) return
    tasks.value = tasks.value.map((task) => {
      if (!refreshedById.has(String(task.id))) return task
      const updated = { ...task, ...refreshedById.get(String(task.id)) }
      if (expandedTaskId.value === task.id && expandedTask.value) {
        expandedTask.value = { ...expandedTask.value, ...updated }
      }
      return updated
    })
  } finally {
    processingRefreshInFlight.value = false
  }
}

function startProcessingRefresh() {
  stopProcessingRefresh()
  processingRefreshTimer.value = window.setInterval(
    refreshProcessingTasks,
    3000
  )
}

function stopProcessingRefresh() {
  if (!processingRefreshTimer.value) return
  window.clearInterval(processingRefreshTimer.value)
  processingRefreshTimer.value = null
}

function goPrevPage() {
  if (tasksLoading.value || currentPage.value <= 1) return
  currentPage.value -= 1
  loadTasks()
}

function goNextPage() {
  if (tasksLoading.value || currentPage.value >= totalPages.value) return
  currentPage.value += 1
  loadTasks()
}

async function toggleTaskExpand(task) {
  if (tasksLoading.value) return
  if (expandedTaskId.value === task.id) {
    expandedTaskId.value = null
    expandedTask.value = null
    return
  }
  expandedTaskId.value = task.id
  expandedTask.value = task
  await loadExpandedTask(task.id)
}

async function loadExpandedTask(id) {
  expandedTaskDetailLoading.value = true
  try {
    const res = await taskManagementApi.getExecution(id)
    const data = extractResponseData(res)
    if (expandedTaskId.value === id) {
      expandedTask.value = data
    }
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error(extractErrorMessage(e, t('common.error')))
  } finally {
    expandedTaskDetailLoading.value = false
  }
}

function formatTrigger(task) {
  const trigger = task?.trigger || task?.metadata?.trigger
  if (trigger === 'manual') {
    return t('lensAdmin.datasourceDetail.details.triggerManual')
  }
  if (trigger === 'periodic' || trigger === 'scheduled') {
    return t('lensAdmin.datasourceDetail.details.triggerScheduled')
  }
  return trigger || t('lensAdmin.datasourceDetail.details.triggerSystem')
}

watch(
  () => [props.datasource?.uuid, props.show, activeTab.value],
  ([uuid, visible, tab]) => {
    if (!visible || !uuid || tab !== 'details') {
      stopProcessingRefresh()
      taskRequestSeq.value += 1
      tasksLoading.value = false
      tasks.value = []
      totalCount.value = 0
      totalPages.value = 1
      expandedTaskId.value = null
      expandedTask.value = null
      return
    }
    stopProcessingRefresh()
    taskRequestSeq.value += 1
    currentPage.value = 1
    tasks.value = []
    totalCount.value = 0
    totalPages.value = 1
    expandedTaskId.value = null
    expandedTask.value = null
    loadTasks().then(() => {
      if (tasks.value.some((task) => isProcessingStatus(task.status))) {
        startProcessingRefresh()
      } else {
        stopProcessingRefresh()
      }
    })
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  stopProcessingRefresh()
})

function formatSourceType(sourceType) {
  if (sourceType === 'git') {
    return 'Git'
  }
  if (sourceType === 'feishu') {
    return t('lensAdmin.datasourceWizard.feishu')
  }
  return sourceType || emptyValue
}

function authSchemeLabel(authScheme) {
  if (authScheme === 'token') {
    return t('lensAdmin.datasourceWizard.authToken')
  }
  return t('lensAdmin.datasourceWizard.authNone')
}

function feishuScopeLabel(syncMode) {
  if (syncMode === 'drive_folder') {
    return t('lensAdmin.datasourceWizard.feishuScopeDriveFolder')
  }
  return t('lensAdmin.datasourceWizard.feishuScopeDocuments')
}

function formatSyncPolicy(syncPolicy) {
  if (syncPolicy?.mode === 'crontab') {
    const cron = syncPolicy.cron || emptyValue
    const timezone = syncPolicy.timezone || 'UTC'
    return `${cron} · ${timezone}`
  }
  const interval = syncPolicy?.interval_seconds
  return interval
    ? t('lensAdmin.table.intervalSeconds', { seconds: interval })
    : emptyValue
}

function lensNodeName(value) {
  const uuid = typeof value === 'object' ? value?.uuid : value
  const found = props.lensnodes.find((lensnode) => lensnode.uuid === uuid)
  return found?.name || uuid || emptyValue
}

function detailItem(label, value, mono = false) {
  const normalized = Array.isArray(value) ? value.join(', ') : value
  return {
    label,
    value: normalized || emptyValue,
    mono
  }
}

const datasourceConnectionDetails = computed(() => {
  const row = props.datasource
  if (!row) return []
  const config = row.config || {}
  if (row.source_type === 'git') {
    return [
      detailItem(t('lensAdmin.fields.type'), formatSourceType(row.source_type)),
      detailItem(t('lensAdmin.fields.repoUrl'), config.repo_url, true),
      detailItem(t('lensAdmin.fields.branch'), config.branch || 'main', true),
      detailItem(
        t('lensAdmin.fields.authScheme'),
        authSchemeLabel(config.auth_scheme)
      ),
      detailItem(
        t('lensAdmin.datasourceDetail.credential'),
        row.credential_configured
          ? t('common.status.enabled')
          : t('common.status.disabled')
      )
    ]
  }
  return [
    detailItem(t('lensAdmin.fields.type'), formatSourceType(row.source_type)),
    detailItem(
      t('lensAdmin.fields.syncScope'),
      feishuScopeLabel(config.sync_mode)
    ),
    detailItem(t('lensAdmin.fields.folderUrl'), config.folder_url, true),
    detailItem(t('lensAdmin.fields.folderToken'), config.folder_token, true),
    detailItem(t('lensAdmin.fields.documentUrl'), config.document_url, true),
    detailItem(t('lensAdmin.fields.docIds'), formatDocIds(config.doc_ids), true)
  ].filter((item) => item.value !== emptyValue)
})

const datasourceSyncDetails = computed(() => {
  const row = props.datasource
  if (!row) return []
  return [
    detailItem(
      t('lensAdmin.fields.lensnode'),
      row.lensnode_name || lensNodeName(row.lensnode)
    ),
    detailItem(t('lensAdmin.fields.targetPath'), row.target_path, true),
    detailItem(
      t('lensAdmin.fields.syncInterval'),
      formatSyncPolicy(row.sync_policy)
    ),
    detailItem(
      t('lensAdmin.datasourceDetail.lastSyncedAt'),
      formatDateTime(row.last_synced_at)
    ),
    detailItem(t('lensAdmin.datasourceDetail.lastError'), row.last_error, true),
    detailItem(
      t('lensAdmin.datasourceDetail.createdAt'),
      formatDateTime(row.created_at)
    ),
    detailItem(
      t('lensAdmin.datasourceDetail.updatedAt'),
      formatDateTime(row.updated_at)
    )
  ]
})
</script>

<style scoped>
.detail-tab {
  @apply border-b-2 border-transparent py-3 text-sm font-medium text-ink-500 transition-colors;
}

.detail-tab:hover {
  @apply text-ink-700;
}

.detail-tab-active {
  @apply border-primary-500 text-primary-600;
}
</style>
