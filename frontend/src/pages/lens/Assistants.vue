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
                {{ t('lensAdmin.pages.assistants.title') }}
              </h1>
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1 text-xs font-medium text-ink-500"
              >
                {{ t('lensAdmin.pages.assistants.label') }}
              </span>
            </div>
            <p class="max-w-3xl text-sm leading-6 text-ink-500">
              {{ t('lensAdmin.pages.assistants.description') }}
            </p>
            <div class="flex flex-wrap items-center gap-2 text-xs text-ink-500">
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1"
              >
                {{
                  t('lensAdmin.total', {
                    label: t('lensAdmin.pages.assistants.label'),
                    count: assistants.length
                  })
                }}
              </span>
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1"
              >
                {{ t('lensAdmin.pages.assistants.action') }}
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
              {{ t('lensAdmin.pages.assistants.action') }}
            </BaseButton>
          </div>
        </div>

        <div class="px-5 py-4">
          <BaseLoading v-if="loading && assistants.length === 0" />

          <div
            v-else-if="assistants.length === 0"
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
                  <th
                    v-for="column in activeColumns"
                    :key="column"
                    class="table-head"
                  >
                    {{ column }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line bg-surface">
                <tr
                  v-for="row in pagedAssistants"
                  :key="row.uuid"
                  class="transition-colors hover:bg-line-soft"
                >
                  <td class="table-cell">
                    <div class="font-medium text-ink-900">
                      {{ row.name }}
                    </div>
                    <div class="mt-1 font-mono text-xs text-ink-400">
                      {{ row.slug }}
                    </div>
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ lensNodeName(row.lensnode) }}
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ row.selected_task || emptyValue }}
                  </td>
                  <td class="table-cell font-mono text-xs text-ink-500">
                    {{ row.selected_dirs?.[0]?.path || emptyValue }}
                  </td>
                  <td class="table-cell text-ink-600">
                    {{
                      t('lensAdmin.table.toolSummary', {
                        skills: row.skill_summary?.enabled || 0,
                        mcps: row.mcp_summary?.enabled || 0
                      })
                    }}
                  </td>
                  <td class="table-cell">
                    <span
                      class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold"
                      :class="
                        row.visibility === 'private'
                          ? 'border-amber-300 bg-amber-100 text-amber-800'
                          : 'border-emerald-300 bg-emerald-100 text-emerald-800'
                      "
                      :title="
                        t(
                          `lensAdmin.visibility.${row.visibility === 'private' ? 'private' : 'public'}Desc`
                        )
                      "
                    >
                      <component
                        :is="
                          row.visibility === 'private' ? LockIcon : GlobeIcon
                        "
                        class="h-3.5 w-3.5"
                      />
                      {{
                        t(
                          `lensAdmin.visibility.${row.visibility === 'private' ? 'private' : 'public'}`
                        )
                      }}
                    </span>
                  </td>
                  <td class="table-cell">
                    <StatusBadge :status="row.status" />
                  </td>
                  <td class="table-cell">
                    <div
                      v-if="row.status === 'active'"
                      class="flex items-center gap-1.5"
                    >
                      <span
                        class="max-w-[220px] truncate font-mono text-xs text-ink-500"
                        :title="shareUrl(row)"
                      >
                        {{ shareUrl(row) }}
                      </span>
                      <button
                        type="button"
                        class="shrink-0 rounded-md p-1.5 text-ink-400 transition-colors hover:bg-surface-sunken hover:text-primary-600"
                        :title="t('lens.share.copyLink')"
                        :aria-label="t('lens.share.copyLink')"
                        @click="copyShareUrl(row)"
                      >
                        <Copy :size="15" :stroke-width="2" aria-hidden="true" />
                      </button>
                    </div>
                    <span v-else class="text-ink-400">{{ emptyValue }}</span>
                  </td>
                  <td class="table-cell">
                    <RowActions :row="row" @edit="startEdit" @delete="remove" />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <PaginationBar
            v-if="!loading"
            v-model:page-size="pageSize"
            :current-page="currentPage"
            :total="assistants.length"
            @page-size-change="handlePageSizeChange"
            @prev="goPrevPage"
            @next="goNextPage"
          />
        </div>
      </section>

      <!-- Assistant Drawer (create wizard + edit) -->
      <AssistantFormDrawer
        :show="showDrawer"
        :mode="mode"
        :form="form"
        :lensnodes="lensnodes"
        :skills="skills"
        :mcps="mcps"
        :llm-config-options="llmConfigOptions"
        :groups="groups"
        :users="users"
        :saving="saving"
        :form-error="formError"
        :refreshing-dirs="refreshingDirs"
        @close="closeDrawer"
        @save="save"
        @refresh-dirs="refreshDirs"
      />
    </div>
  </AdminLayout>
</template>

<script setup>
import { Copy, Globe as GlobeIcon, Lock as LockIcon } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { llmAdminApi } from '@/admin/api/llmAdmin'
import { managementApi } from '@/admin/api/management'
import { copyToClipboard } from '@/utils/clipboard'
import { extractErrorMessage } from '@/utils/api'
import { assistantChatUrl } from '@/utils/lens'
import AdminLayout from '@/admin/layout/AdminLayout.vue'
import {
  createAssistant,
  deleteAssistant,
  listAssistants,
  listGlobalSettings,
  listLensNodes,
  listMcpServers,
  listSkills,
  updateAssistant
} from '@/api/lens'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'

import AssistantFormDrawer from './AssistantFormDrawer.vue'
import RowActions from './components/RowActions.vue'
import {
  EMPTY_VALUE as emptyValue,
  listToText,
  normalizeList,
  selectedDirsFromValue,
  splitList
} from './adminHelpers'

const { t } = useI18n()
const { showSuccess, showError } = useToast()

const loading = ref(false)
const saving = ref(false)
const refreshingDirs = ref(false)
const showDrawer = ref(false)
const mode = ref('create')
const form = ref({})
const formError = ref('')

const assistants = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const lensnodes = ref([])
const skills = ref([])
const mcps = ref([])
const globalSettings = ref([])
const llmConfigOptions = ref([])
const groups = ref([])
const users = ref([])

const activeColumns = computed(() =>
  [
    'assistant',
    'lensnode',
    'task',
    'dirs',
    'tools',
    'visibility',
    'status',
    'shareUrl',
    'actions'
  ].map((column) => t(`lensAdmin.columns.${column}`))
)

const totalPages = computed(() =>
  Math.max(1, Math.ceil(assistants.value.length / pageSize.value))
)
const pagedAssistants = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return assistants.value.slice(start, start + pageSize.value)
})

function handlePageSizeChange() {
  currentPage.value = 1
}

function goPrevPage() {
  if (currentPage.value <= 1) return
  currentPage.value -= 1
}

function goNextPage() {
  if (currentPage.value >= totalPages.value) return
  currentPage.value += 1
}

function lensNodeName(value) {
  const uuid = typeof value === 'object' ? value?.uuid : value
  const found = lensnodes.value.find((lensnode) => lensnode.uuid === uuid)
  return found?.name || uuid || emptyValue
}

function shareUrl(row) {
  return assistantChatUrl(row.slug, globalSettings.value)
}

async function copyShareUrl(row) {
  if (await copyToClipboard(shareUrl(row))) {
    showSuccess(t('lens.share.copied'))
  } else {
    showError(t('lens.share.copyFailed'))
  }
}

function selectedDirs() {
  return Array.isArray(form.value.selected_dirs) ? form.value.selected_dirs : []
}

async function load() {
  loading.value = true
  formError.value = ''
  try {
    const [
      assistantRows,
      lensnodeRows,
      skillRows,
      mcpRows,
      settingRows,
      llmRows,
      groupRows,
      userRows
    ] = await Promise.all([
      listAssistants(),
      listLensNodes(),
      listSkills(),
      listMcpServers(),
      listGlobalSettings(),
      llmAdminApi.getLLMConfigAll({ scope: 'global' }).catch(() => []),
      managementApi.getGroups({ page_size: 1000 }).catch(() => []),
      managementApi.getUsers({ page_size: 1000 }).catch(() => [])
    ])

    assistants.value = normalizeList(assistantRows)
    lensnodes.value = normalizeList(lensnodeRows)
    skills.value = normalizeList(skillRows)
    mcps.value = normalizeList(mcpRows)
    globalSettings.value = normalizeList(settingRows)
    llmConfigOptions.value = normalizeList(llmRows)
    groups.value = normalizeList(groupRows)
    users.value = normalizeList(userRows)
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.loadFailed')))
  } finally {
    loading.value = false
  }
}

function startCreate() {
  mode.value = 'create'
  formError.value = ''
  form.value = defaultForm()
  showDrawer.value = true
}

function startEdit(row) {
  mode.value = 'edit'
  formError.value = ''
  form.value = formFromRow(row)
  showDrawer.value = true
}

function closeDrawer() {
  showDrawer.value = false
  form.value = {}
  formError.value = ''
}

async function refreshDirs() {
  if (!form.value.lensnode_uuid) return
  refreshingDirs.value = true
  try {
    lensnodes.value = normalizeList(await listLensNodes())
  } catch {
    showError(t('lensAdmin.messages.loadFailed'))
  } finally {
    refreshingDirs.value = false
  }
}

function defaultForm() {
  return {
    name: '',
    slug: '',
    lensnode_uuid: '',
    selected_task: '',
    selected_dirs: [],
    agent_model_ref: '',
    agent_rounds: 'balanced',
    max_concurrency: 5,
    multimodal_model_ref: '',
    exclude_extensions_text: '.lock,.pyc,.sqlite3',
    exclude_dirs_text: '.git,.venv,__pycache__,node_modules,dist,build',
    workspace_guide_overview: '',
    pre_prompt: '',
    post_prompt: '',
    skill_uuids: [],
    mcp_uuids: [],
    visibility: 'private',
    access_group_ids: [],
    access_user_ids: [],
    settings: {},
    status: 'active'
  }
}

function workspaceGuideSkillUuids() {
  return new Set(
    skills.value
      .filter(
        (s) => typeof s.slug === 'string' && s.slug.endsWith('-workspace-guide')
      )
      .map((s) => s.uuid)
  )
}

function formFromRow(row) {
  const wgUuids = workspaceGuideSkillUuids()
  return {
    uuid: row.uuid,
    name: row.name || '',
    slug: row.slug || '',
    lensnode_uuid: row.lensnode?.uuid || row.lensnode || '',
    selected_task: row.selected_task || '',
    selected_dirs: selectedDirsFromValue(row.selected_dirs || []),
    agent_model_ref: row.agent_model_ref || '',
    agent_rounds: row.agent_rounds || 'balanced',
    max_concurrency: row.max_concurrency ?? 5,
    multimodal_model_ref: row.multimodal_model_ref || '',
    exclude_extensions_text: listToText(
      row.settings?.retrieval_policy?.exclude_extensions || [
        '.lock',
        '.pyc',
        '.sqlite3'
      ]
    ),
    exclude_dirs_text: listToText(
      row.settings?.retrieval_policy?.exclude_dirs || [
        '.git',
        '.venv',
        '__pycache__',
        'node_modules',
        'dist',
        'build'
      ]
    ),
    workspace_guide_overview: row.workspace_guide?.content || '',
    pre_prompt: row.settings?.pre_prompt || '',
    post_prompt: row.settings?.post_prompt || '',
    skill_uuids: (row.skill_bindings || [])
      .map((b) => b.skill?.uuid || b.skill_uuid)
      .filter((u) => u && !wgUuids.has(u)),
    mcp_uuids: (row.mcp_bindings || [])
      .map((b) => b.mcp_server?.uuid || b.mcp_uuid)
      .filter(Boolean),
    visibility: row.visibility || 'public',
    access_group_ids: (row.access_grants || [])
      .filter((g) => g.type === 'group')
      .map((g) => g.id),
    access_user_ids: (row.access_grants || [])
      .filter((g) => g.type === 'user')
      .map((g) => g.id),
    settings: { ...(row.settings || {}) },
    status: row.status || 'active'
  }
}

async function save() {
  saving.value = true
  formError.value = ''
  try {
    const payload = buildPayload()
    const uuid = form.value.uuid
    await saveByMode(uuid, payload, createAssistant, updateAssistant)
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

async function saveByMode(uuid, payload, createFn, updateFn) {
  if (mode.value === 'create') {
    await createFn(payload)
  } else {
    await updateFn(uuid, payload)
  }
}

function buildPayload() {
  const guideContent = (form.value.workspace_guide_overview || '').trim()
  return {
    name: form.value.name,
    slug: form.value.slug,
    lensnode_uuid: form.value.lensnode_uuid,
    selected_task: form.value.selected_task,
    selected_dirs:
      form.value.selected_task === 'general_chat' ? [] : buildSelectedDirs(),
    agent_model_ref: form.value.agent_model_ref || null,
    agent_rounds: form.value.agent_rounds || 'balanced',
    max_concurrency: Number(form.value.max_concurrency) || 5,
    multimodal_model_ref: form.value.multimodal_model_ref || null,
    settings: buildAssistantSettings(),
    workspace_guide: {
      enabled: form.value.selected_task !== 'general_chat' && !!guideContent,
      content: guideContent
    },
    skill_bindings: (form.value.skill_uuids || []).map((uuid) => ({
      skill_uuid: uuid
    })),
    mcp_bindings: (form.value.mcp_uuids || []).map((uuid) => ({
      mcp_uuid: uuid
    })),
    visibility: form.value.visibility || 'public',
    access_grants: buildAccessGrants(),
    status: form.value.status || 'active'
  }
}

function buildAccessGrants() {
  if (form.value.visibility !== 'private') {
    return []
  }
  return [
    ...(form.value.access_group_ids || []).map((id) => ({
      type: 'group',
      id
    })),
    ...(form.value.access_user_ids || []).map((id) => ({
      type: 'user',
      id
    }))
  ]
}

function buildAssistantSettings() {
  const settings = { ...(form.value.settings || {}) }
  const retrievalPolicy = {}
  const excludeExtensions = splitList(form.value.exclude_extensions_text)
  const excludeDirs = splitList(form.value.exclude_dirs_text)
  if (excludeExtensions.length) {
    retrievalPolicy.exclude_extensions = excludeExtensions
  }
  if (excludeDirs.length) {
    retrievalPolicy.exclude_dirs = excludeDirs
  }
  settings.retrieval_policy = retrievalPolicy
  if (form.value.pre_prompt?.trim()) {
    settings.pre_prompt = form.value.pre_prompt.trim()
  } else {
    delete settings.pre_prompt
  }
  if (form.value.post_prompt?.trim()) {
    settings.post_prompt = form.value.post_prompt.trim()
  } else {
    delete settings.post_prompt
  }
  return settings
}

function buildSelectedDirs() {
  return selectedDirs().map((dir) => {
    const includePaths = String(dir.include_paths_text || '')
      .split('\n')
      .map((item) => item.trim())
      .filter(Boolean)
    if (!includePaths.length) {
      return { path: dir.path }
    }
    return {
      path: dir.path,
      retrieval_scope: { include_paths: includePaths }
    }
  })
}

async function remove(row) {
  try {
    await deleteAssistant(row.uuid)
    showSuccess(t('lensAdmin.messages.deleteSuccess'))
    await load()
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.deleteFailed')))
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
