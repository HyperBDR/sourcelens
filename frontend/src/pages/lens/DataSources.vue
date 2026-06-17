<template>
  <AdminLayout>
    <div class="flex max-w-full flex-col gap-4 py-4">
      <section
        class="overflow-hidden rounded-lg border border-line bg-surface shadow-sm"
      >
        <div
          class="flex flex-col gap-4 border-b border-line px-5 py-4 lg:flex-row lg:items-start lg:justify-between"
        >
          <div class="min-w-0 space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-xl font-semibold text-ink-900">
                {{ t('lensAdmin.pages.datasources.title') }}
              </h1>
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1 text-xs font-medium text-ink-500"
              >
                {{ t('lensAdmin.pages.datasources.label') }}
              </span>
            </div>
            <p class="max-w-3xl text-sm leading-6 text-ink-500">
              {{ t('lensAdmin.pages.datasources.description') }}
            </p>
            <div class="flex flex-wrap items-center gap-2 text-xs text-ink-500">
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1"
              >
                {{
                  t('lensAdmin.total', {
                    label: t('lensAdmin.pages.datasources.label'),
                    count: dataSources.length
                  })
                }}
              </span>
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1"
              >
                {{ t('lensAdmin.pages.datasources.action') }}
              </span>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <BaseButton
              variant="outline"
              size="sm"
              :loading="loading"
              @click="load"
            >
              {{ t('common.refresh') }}
            </BaseButton>
            <BaseButton variant="primary" size="sm" @click="startCreate">
              {{ t('lensAdmin.pages.datasources.action') }}
            </BaseButton>
          </div>
        </div>

        <div class="px-5 py-4">
          <BaseLoading v-if="loading && dataSources.length === 0" />

          <div
            v-else-if="dataSources.length === 0"
            class="rounded-lg border border-line bg-surface-sunken py-16 text-center"
          >
            <p class="text-sm font-medium text-ink-500">
              {{ t('common.noData') }}
            </p>
          </div>

          <div
            v-else
            class="relative overflow-x-auto rounded-lg border border-line bg-surface"
          >
            <table class="min-w-full divide-y divide-line">
              <thead class="bg-surface-sunken">
                <tr>
                  <th class="table-head">
                    {{ t('lensAdmin.columns.datasource') }}
                  </th>
                  <th class="table-head">
                    {{ t('lensAdmin.columns.repository') }}
                  </th>
                  <th class="table-head">
                    {{ t('lensAdmin.columns.lensnode') }}
                  </th>
                  <th class="table-head">
                    {{ t('lensAdmin.columns.targetPath') }}
                  </th>
                  <th class="table-head">
                    {{ t('lensAdmin.columns.status') }}
                  </th>
                  <th class="table-head">
                    {{ t('lensAdmin.columns.policy') }}
                  </th>
                  <th class="table-head">
                    {{ t('lensAdmin.columns.actions') }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line bg-surface">
                <tr
                  v-for="row in dataSources"
                  :key="row.uuid"
                  class="cursor-pointer transition-colors hover:bg-line-soft"
                  :class="
                    selectedDataSource?.uuid === row.uuid ? 'bg-brand-50' : ''
                  "
                  @click="selectDataSource(row)"
                >
                  <td class="table-cell">
                    <div
                      class="flex items-center gap-2 font-medium text-ink-900"
                    >
                      <span
                        :class="
                          isDataSourceEnabled(row)
                            ? 'bg-success-600'
                            : 'bg-danger-600'
                        "
                        class="h-2 w-2 shrink-0 rounded-full"
                      />
                      <span>{{ row.name }}</span>
                    </div>
                    <div class="mt-1 flex flex-wrap items-center gap-2">
                      <span class="font-mono text-xs text-ink-400">
                        {{ compactUuid(row.uuid) }}
                      </span>
                      <span
                        class="rounded border border-line bg-surface-sunken px-1.5 py-0.5 text-xs text-ink-500"
                      >
                        {{ formatSourceType(row.source_type) }}
                      </span>
                    </div>
                  </td>
                  <td class="table-cell max-w-xs text-ink-600">
                    <div class="truncate" :title="dataSourceRepository(row)">
                      {{ dataSourceRepository(row) }}
                    </div>
                    <div
                      v-if="row.source_type === 'git'"
                      class="mt-1 font-mono text-xs text-ink-500"
                    >
                      {{ dataSourceBranch(row) }}
                    </div>
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ row.lensnode_name || lensNodeName(row.lensnode) }}
                  </td>
                  <td
                    class="table-cell max-w-xs font-mono text-xs text-ink-500"
                  >
                    <div
                      class="truncate"
                      :title="row.target_path || emptyValue"
                    >
                      {{ row.target_path || emptyValue }}
                    </div>
                  </td>
                  <td class="table-cell text-ink-600">
                    <div class="flex max-w-sm flex-col items-start gap-2">
                      <div class="flex flex-wrap gap-1.5">
                        <span
                          v-for="tag in datasourceSyncTags(row)"
                          :key="tag.key"
                          :class="tag.class"
                          class="inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium"
                        >
                          {{ tag.label }}
                        </span>
                      </div>
                      <div
                        v-if="isDataSourceSyncing(row)"
                        class="space-y-1 text-xs text-ink-500"
                      >
                        <div class="break-words">
                          {{
                            row.current_sync?.progress_message ||
                            row.current_sync?.progress_step ||
                            emptyValue
                          }}
                        </div>
                        <div class="font-mono">
                          {{ compactUuid(row.current_sync?.task_id) }}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td class="table-cell">
                    <div class="space-y-1 text-xs text-ink-500">
                      <div class="font-mono text-ink-700">
                        {{ formatDataSourcePolicyLine(row.sync_policy) }}
                      </div>
                      <div>
                        {{ t('lensAdmin.table.lastSync') }}:
                        {{ formatDateTime(row.last_synced_at) }}
                      </div>
                      <div>
                        {{ t('lensAdmin.table.nextSync') }}:
                        {{ formatNextDatasourceSync(row) }}
                      </div>
                    </div>
                  </td>
                  <td class="table-cell" @click.stop>
                    <div class="flex flex-wrap gap-2">
                      <BaseButton
                        size="sm"
                        variant="outline"
                        :disabled="
                          !isDataSourceEnabled(row) || isDataSourceSyncing(row)
                        "
                        @click="sync(row)"
                      >
                        {{ t('lensAdmin.actions.sync') }}
                      </BaseButton>
                      <BaseButton
                        size="sm"
                        :variant="
                          isDataSourceEnabled(row) ? 'outline' : 'primary'
                        "
                        @click="toggleDataSourceEnabled(row)"
                      >
                        {{
                          isDataSourceEnabled(row)
                            ? t('lensAdmin.actions.disableDatasource')
                            : t('lensAdmin.actions.enableDatasource')
                        }}
                      </BaseButton>
                      <BaseButton
                        v-if="isDataSourceSyncing(row)"
                        size="sm"
                        variant="danger"
                        @click="cancelSync(row)"
                      >
                        {{ t('lensAdmin.actions.cancelSync') }}
                      </BaseButton>
                      <RowActions
                        :row="row"
                        @edit="startEdit"
                        @delete="remove"
                      />
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <DataSourceFormDrawer
        :show="showDrawer"
        :mode="mode"
        :form="form"
        :config="datasourceConfig"
        :lensnodes="lensnodes"
        :credentials="credentials"
        v-model:sync-interval-seconds="syncIntervalSeconds"
        v-model:sync-policy-mode="syncPolicyMode"
        v-model:sync-cron="syncCron"
        v-model:sync-timezone="syncTimezone"
        :path-result="datasourcePathResult"
        :connection-result="datasourceConnectionResult"
        :checking-path="checkingDatasourcePath"
        :testing-connection="testingDatasourceConnection"
        :saving="saving"
        :form-error="formError"
        @close="closeDrawer"
        @save="save"
        @type-change="handleDatasourceTypeChange"
        @check-path="checkDatasourcePath"
        @test-connection="testDatasourceConnection"
        @connection-change="resetDatasourceConnectionResult"
        @create-credential="createInlineCredential"
      />

      <DataSourceDetailDrawer
        :show="showDatasourceDetailDrawer"
        :datasource="selectedDataSource"
        :lensnodes="lensnodes"
        @close="closeDataSourceDetail"
      />
    </div>
  </AdminLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractErrorMessage } from '@/utils/api'
import AdminLayout from '@/admin/layout/AdminLayout.vue'
import {
  cancelDataSourceSync,
  checkLensNodeDataSourcePath,
  createCredential,
  createDataSource,
  deleteDataSource,
  listCredentials,
  listDataSources,
  listLensNodes,
  setDataSourceEnabled,
  syncDataSource,
  testLensNodeDataSourceConnection,
  updateDataSource
} from '@/api/lens'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'

import DataSourceDetailDrawer from './DataSourceDetailDrawer.vue'
import DataSourceFormDrawer from './DataSourceFormDrawer.vue'
import RowActions from './components/RowActions.vue'
import {
  EMPTY_VALUE as emptyValue,
  compactUuid,
  normalizeList
} from './adminHelpers'
import {
  dataSourceBranch,
  dataSourceRepository,
  formatDataSourcePolicyLine,
  isDataSourceEnabled,
  isDataSourceSyncing,
  syncTagClass
} from './datasourceHelpers'
import { useShortDateTime } from './useShortDateTime'

const { t } = useI18n()
const { showSuccess, showError } = useToast()

const loading = ref(false)
const saving = ref(false)
const mode = ref('create')
const form = ref({})
const formError = ref('')
const showDrawer = ref(false)
const showDatasourceDetailDrawer = ref(false)

const dataSources = ref([])
const lensnodes = ref([])
const credentials = ref([])
const selectedDataSource = ref(null)

const datasourceConfig = ref({})
const datasourcePathResult = ref(null)
const datasourceConnectionResult = ref(null)
const suppressDatasourceConnectionReset = ref(false)
const datasourceConnectionBaseSignature = ref('')
const checkingDatasourcePath = ref(false)
const testingDatasourceConnection = ref(false)
const syncIntervalSeconds = ref(3600)
const syncPolicyMode = ref('interval')
const syncCron = ref('0 2 * * *')
const syncTimezone = ref('Asia/Shanghai')

const formatDateTime = useShortDateTime()

const selectedDatasourceLensNode = computed(() =>
  lensnodes.value.find((node) => node.uuid === form.value.lensnode_uuid)
)

function datasourceSyncTags(row) {
  const tags = []
  if (!isDataSourceEnabled(row)) {
    tags.push({
      key: 'disabled',
      label: t('common.status.disabled'),
      class: syncTagClass('disabled')
    })
  } else if (isDataSourceSyncing(row)) {
    tags.push({
      key: 'running',
      label: t('lensAdmin.table.syncRunning'),
      class: syncTagClass('running')
    })
  } else {
    const status = row.sync_state?.last_status || ''
    tags.push({
      key: 'last-status',
      label: formatDatasourceLastSyncStatus(status),
      class: syncTagClass(status || 'not_synced')
    })
  }
  return tags
}

function formatDatasourceLastSyncStatus(status) {
  if (status === 'success') {
    return t('common.status.success')
  }
  if (status === 'failed') {
    return t('common.status.failed')
  }
  return t('lensAdmin.table.notSynced')
}

function formatNextDatasourceSync(row) {
  if (!isDataSourceEnabled(row)) {
    return t('common.status.disabled')
  }
  if (row.sync_state?.next_run_at) {
    return formatDateTime(row.sync_state.next_run_at)
  }
  if (row.sync_policy?.mode === 'crontab') {
    return t('lensAdmin.table.followCrontab')
  }
  return t('lensAdmin.table.notRecorded')
}

function selectDataSource(row) {
  selectedDataSource.value = row
  showDatasourceDetailDrawer.value = true
}

function closeDataSourceDetail() {
  showDatasourceDetailDrawer.value = false
}

function formatSourceType(sourceType) {
  if (sourceType === 'git') {
    return 'Git'
  }
  if (sourceType === 'feishu') {
    return t('lensAdmin.datasourceWizard.feishu')
  }
  return sourceType || emptyValue
}

function lensNodeName(value) {
  const uuid = typeof value === 'object' ? value?.uuid : value
  const found = lensnodes.value.find((lensnode) => lensnode.uuid === uuid)
  return found?.name || uuid || emptyValue
}

async function load() {
  loading.value = true
  formError.value = ''
  try {
    const [dataSourceRows, lensnodeRows, credentialRows] = await Promise.all([
      listDataSources(),
      listLensNodes(),
      listCredentials()
    ])
    dataSources.value = normalizeList(dataSourceRows)
    lensnodes.value = normalizeList(lensnodeRows)
    credentials.value = normalizeList(credentialRows)
    const existing = dataSources.value.find(
      (row) => row.uuid === selectedDataSource.value?.uuid
    )
    selectedDataSource.value = existing || dataSources.value[0] || null
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.loadFailed')))
  } finally {
    loading.value = false
  }
}

function startCreate() {
  showDatasourceDetailDrawer.value = false
  mode.value = 'create'
  formError.value = ''
  datasourceConfig.value = {}
  datasourcePathResult.value = null
  datasourceConnectionResult.value = null
  syncIntervalSeconds.value = 3600
  form.value = defaultForm()
  showDrawer.value = true
}

function startEdit(row) {
  showDatasourceDetailDrawer.value = false
  mode.value = 'edit'
  formError.value = ''
  datasourceConfig.value = { ...(row.config || {}) }
  datasourcePathResult.value = null
  datasourceConnectionResult.value = null
  syncIntervalSeconds.value = row.sync_policy?.interval_seconds || 3600
  form.value = formFromRow(row)
  showDrawer.value = true
}

function closeDrawer() {
  showDrawer.value = false
  form.value = {}
  formError.value = ''
  datasourcePathResult.value = null
  datasourceConnectionResult.value = null
  resetDatasourceSyncPolicy()
}

function defaultForm() {
  const seed = {
    name: '',
    source_type: 'git',
    lensnode_uuid: '',
    workspace_relative_path: '',
    target_path: '',
    credential_uuid: '',
    credential_configured: false,
    status: 'active'
  }
  handleDatasourceTypeChange(seed)
  return seed
}

function formFromRow(row) {
  const lensnodeUuid = row.lensnode?.uuid || row.lensnode || ''
  datasourceConfig.value = datasourceConfigFromRow(row)
  hydrateDatasourceSyncPolicy(row.sync_policy || {})
  return {
    uuid: row.uuid,
    name: row.name || '',
    source_type: row.source_type || 'git',
    lensnode_uuid: lensnodeUuid,
    workspace_relative_path: workspaceRelativePath(
      row.target_path || '',
      lensnodeUuid
    ),
    target_path: row.target_path || '',
    credential_uuid: row.credential || '',
    credential_configured: !!row.credential_configured,
    status: row.status || 'active'
  }
}

function datasourceConfigFromRow(row) {
  if (row.source_type === 'feishu') {
    return {
      ...(row.config || {}),
      sync_mode: row.config?.sync_mode || 'document_list',
      doc_ids_text: (row.config?.doc_ids || []).join(','),
      recursive: row.config?.recursive !== false,
      max_depth: row.config?.max_depth || 10
    }
  }
  const config = { ...(row.config || {}) }
  delete config.access_token
  return config
}

function handleDatasourceTypeChange(seed = null) {
  datasourcePathResult.value = null
  datasourceConnectionResult.value = null
  resetDatasourceSyncPolicy()
  if (!seed) {
    form.value.credential_uuid = ''
  }
  const sourceType = seed?.source_type || form.value.source_type
  if (sourceType === 'git') {
    datasourceConfig.value = {
      repo_url: '',
      branch: '',
      auth_scheme: 'none'
    }
  } else if (sourceType === 'feishu') {
    datasourceConfig.value = {
      sync_mode: 'document_list',
      document_url: '',
      doc_ids_text: '',
      folder_url: '',
      folder_token: '',
      recursive: true,
      max_depth: 10
    }
  }
}

function resetDatasourceSyncPolicy() {
  syncPolicyMode.value = 'interval'
  syncIntervalSeconds.value = 3600
  syncCron.value = '0 2 * * *'
  syncTimezone.value = 'Asia/Shanghai'
}

function hydrateDatasourceSyncPolicy(syncPolicy) {
  if ((syncPolicy.mode || 'interval') === 'crontab') {
    syncPolicyMode.value = 'crontab'
    syncCron.value = syncPolicy.cron || '0 2 * * *'
    syncTimezone.value = syncPolicy.timezone || 'Asia/Shanghai'
    return
  }
  syncPolicyMode.value = 'interval'
  syncIntervalSeconds.value = Number(syncPolicy.interval_seconds) || 3600
  syncCron.value = '0 2 * * *'
  syncTimezone.value = 'Asia/Shanghai'
}

async function save() {
  saving.value = true
  formError.value = ''
  try {
    if (!canSaveDatasource()) {
      throw new Error(t('lensAdmin.datasourceWizard.connectionRequired'))
    }
    const payload = buildPayload()
    const uuid = form.value.uuid
    if (mode.value === 'create') {
      await createDataSource(payload)
    } else {
      await updateDataSource(uuid, payload)
    }
    showSuccess(t('lensAdmin.messages.saveSuccess'))
    closeDrawer()
    await load()
  } catch (error) {
    formError.value = extractErrorMessage(
      error,
      t('lensAdmin.messages.saveFailed')
    )
    showError(formError.value)
  } finally {
    saving.value = false
  }
}

function buildPayload() {
  return {
    name: form.value.name,
    source_type: form.value.source_type,
    lensnode_uuid: form.value.lensnode_uuid,
    target_path: datasourceTargetPath(),
    config: buildDatasourceConfig(),
    sync_policy: buildDatasourceSyncPolicy(),
    status: form.value.status || 'active',
    credential_uuid: shouldUseDatasourceCredential()
      ? form.value.credential_uuid
      : null
  }
}

function buildDatasourceConfig() {
  const config = { ...datasourceConfig.value }
  if (form.value.source_type === 'feishu') {
    config.doc_ids = String(config.doc_ids_text || '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    delete config.doc_ids_text
    if (config.sync_mode !== 'drive_folder') {
      delete config.folder_url
      delete config.folder_token
      delete config.recursive
      delete config.max_depth
    } else {
      delete config.document_url
      delete config.doc_ids
    }
    delete config.app_token
    delete config.app_id
    delete config.app_secret
  }
  return config
}

function buildDatasourceSyncPolicy() {
  if (syncPolicyMode.value === 'crontab') {
    return {
      mode: 'crontab',
      cron: String(syncCron.value || '').trim(),
      timezone: String(syncTimezone.value || '').trim() || 'UTC'
    }
  }
  return {
    mode: 'interval',
    interval_seconds: Math.max(1, Number(syncIntervalSeconds.value) || 3600)
  }
}

function datasourceTargetPath() {
  const relative = String(form.value.workspace_relative_path || '').trim()
  const workspace = datasourceWorkspaceRoot()
  return relative ? `${workspace}/${relative}` : ''
}

function workspaceRelativePath(targetPath, lensnodeUuid = null) {
  const value = String(targetPath || '').trim()
  const workspace = datasourceWorkspaceRoot(lensnodeUuid)
  if (value.startsWith(`${workspace}/`)) {
    return value.slice(workspace.length + 1)
  }
  return value
}

function datasourceWorkspaceRoot(lensnodeUuid = null) {
  const lensnode = lensnodeUuid
    ? lensnodes.value.find((node) => node.uuid === lensnodeUuid)
    : selectedDatasourceLensNode.value
  return String(lensnode?.workspace_path || '/workspace').replace(/\/+$/, '')
}

async function checkDatasourcePath() {
  if (!form.value.lensnode_uuid || !form.value.workspace_relative_path) return
  checkingDatasourcePath.value = true
  datasourcePathResult.value = null
  try {
    datasourcePathResult.value = await checkLensNodeDataSourcePath(
      form.value.lensnode_uuid,
      {
        target_path: datasourceTargetPath(),
        source_type: form.value.source_type,
        config: buildDatasourceConfig()
      }
    )
  } catch (error) {
    datasourcePathResult.value = {
      status: 'blocked',
      message: extractErrorMessage(error, t('lensAdmin.messages.loadFailed'))
    }
  } finally {
    checkingDatasourcePath.value = false
  }
}

function canSaveDatasource() {
  return datasourceConnectionResult.value?.status === 'success'
}

function resetDatasourceConnectionResult() {
  if (suppressDatasourceConnectionReset.value) {
    suppressDatasourceConnectionReset.value = false
    return
  }
  if (shouldKeepGitBranchConnectionResult()) {
    datasourceConnectionResult.value = {
      ...datasourceConnectionResult.value,
      details: {
        ...(datasourceConnectionResult.value?.details || {}),
        branch: datasourceConfig.value.branch
      }
    }
    return
  }
  datasourceConnectionResult.value = null
  datasourceConnectionBaseSignature.value = ''
}

async function testDatasourceConnection() {
  if (!form.value.lensnode_uuid) return
  testingDatasourceConnection.value = true
  datasourceConnectionResult.value = null
  try {
    const result = await testLensNodeDataSourceConnection(
      form.value.lensnode_uuid,
      {
        datasource_uuid: form.value.uuid || null,
        credential_uuid: shouldUseDatasourceCredential()
          ? form.value.credential_uuid
          : null,
        source_type: form.value.source_type,
        config: buildDatasourceConfig()
      }
    )
    applyDatasourceConnectionResult(result)
    datasourceConnectionResult.value = result
    datasourceConnectionBaseSignature.value =
      datasourceConnectionSignature(true)
  } catch (error) {
    datasourceConnectionResult.value = {
      status: 'failed',
      message: extractErrorMessage(error, t('lensAdmin.messages.loadFailed'))
    }
  } finally {
    testingDatasourceConnection.value = false
  }
}

function shouldUseDatasourceCredential() {
  if (!form.value.credential_uuid) {
    return false
  }
  if (form.value.source_type === 'git') {
    return datasourceConfig.value.auth_scheme === 'token'
  }
  return form.value.source_type === 'feishu'
}

async function createInlineCredential(payload) {
  try {
    const credential = await createCredential(payload)
    credentials.value = [credential, ...credentials.value]
    form.value.credential_uuid = credential.uuid
    showSuccess(t('lensAdmin.messages.saveSuccess'))
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.saveFailed')))
  }
}

function applyDatasourceConnectionResult(result) {
  if (form.value.source_type !== 'git' || result?.status !== 'success') {
    return
  }
  const branches = result?.details?.branches
  if (!Array.isArray(branches) || branches.length !== 1) {
    return
  }
  const branch = branches[0]
  if (datasourceConfig.value.branch !== branch) {
    suppressDatasourceConnectionReset.value = true
    datasourceConfig.value.branch = branch
  }
}

function shouldKeepGitBranchConnectionResult() {
  if (
    form.value.source_type !== 'git' ||
    datasourceConnectionResult.value?.status !== 'success'
  ) {
    return false
  }
  if (
    datasourceConnectionSignature(true) !==
    datasourceConnectionBaseSignature.value
  ) {
    return false
  }
  const branches = datasourceConnectionResult.value?.details?.branches
  return (
    Array.isArray(branches) && branches.includes(datasourceConfig.value.branch)
  )
}

function datasourceConnectionSignature(ignoreBranch = false) {
  const config = buildDatasourceConfig()
  if (ignoreBranch) {
    delete config.branch
  }
  return JSON.stringify({
    lensnode_uuid: form.value.lensnode_uuid || '',
    source_type: form.value.source_type || '',
    config
  })
}

async function remove(row) {
  try {
    await deleteDataSource(row.uuid)
    if (selectedDataSource.value?.uuid === row.uuid) {
      selectedDataSource.value = null
      showDatasourceDetailDrawer.value = false
    }
    showSuccess(t('lensAdmin.messages.deleteSuccess'))
    await load()
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.deleteFailed')))
  }
}

async function sync(row) {
  if (!isDataSourceEnabled(row)) {
    showError(t('lensAdmin.messages.datasourceDisabled'))
    return
  }
  try {
    const result = await syncDataSource(row.uuid)
    const taskId = result?.task_id || ''
    showSuccess(
      taskId
        ? `${t('lensAdmin.messages.syncStarted')} (${taskId})`
        : t('lensAdmin.messages.syncStarted')
    )
    await load()
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.syncFailed')))
  }
}

async function toggleDataSourceEnabled(row) {
  try {
    await setDataSourceEnabled(row.uuid, !isDataSourceEnabled(row))
    showSuccess(t('lensAdmin.messages.saveSuccess'))
    await load()
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.saveFailed')))
  }
}

async function cancelSync(row) {
  try {
    const result = await cancelDataSourceSync(row.uuid)
    const taskId = result?.task_id || row.current_sync?.task_id || ''
    showSuccess(
      taskId
        ? `${t('lensAdmin.messages.syncCancelled')} (${taskId})`
        : t('lensAdmin.messages.syncCancelled')
    )
    await load()
  } catch (error) {
    showError(
      extractErrorMessage(error, t('lensAdmin.messages.syncCancelFailed'))
    )
  }
}

onMounted(load)
</script>

<style scoped>
.table-head {
  @apply border-b border-line px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-500;
}

.table-cell {
  @apply px-4 py-4 text-sm text-ink-700;
}
</style>
