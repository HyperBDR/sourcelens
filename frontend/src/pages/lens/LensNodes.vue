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
                {{ t('lensAdmin.pages.lensnodes.title') }}
              </h1>
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1 text-xs font-medium text-ink-500"
              >
                {{ t('lensAdmin.pages.lensnodes.label') }}
              </span>
            </div>
            <p class="max-w-3xl text-sm leading-6 text-ink-500">
              {{ t('lensAdmin.pages.lensnodes.description') }}
            </p>
            <div class="flex flex-wrap items-center gap-2 text-xs text-ink-500">
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1"
              >
                {{
                  t('lensAdmin.total', {
                    label: t('lensAdmin.pages.lensnodes.label'),
                    count: lensnodes.length
                  })
                }}
              </span>
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1"
              >
                {{ t('lensAdmin.pages.lensnodes.action') }}
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
              {{ t('lensAdmin.pages.lensnodes.action') }}
            </BaseButton>
          </div>
        </div>

        <div class="px-5 py-4">
          <BaseLoading v-if="loading && lensnodes.length === 0" />

          <div
            v-else-if="lensnodes.length === 0"
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
                    v-for="column in columns"
                    :key="column"
                    class="table-head"
                  >
                    {{ column }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line bg-surface">
                <tr
                  v-for="row in pagedLensNodes"
                  :key="row.uuid"
                  class="transition-colors hover:bg-line-soft"
                >
                  <td class="table-cell">
                    <button
                      type="button"
                      class="group text-left"
                      :title="t('lensAdmin.detail.title')"
                      @click="openDetail(row)"
                    >
                      <div
                        class="font-medium text-ink-900 group-hover:text-primary-600 group-hover:underline"
                      >
                        {{ row.name }}
                      </div>
                      <div class="mt-1 font-mono text-xs text-ink-400">
                        {{ compactUuid(row.uuid) }}
                      </div>
                    </button>
                  </td>
                  <td class="table-cell">
                    <StatusBadge :status="row.status" />
                  </td>
                  <td class="table-cell">
                    <div class="flex flex-wrap items-center gap-2">
                      <StatusBadge :status="row.enrollment_status" />
                      <template v-if="row.enrollment_status === 'pending'">
                        <BaseButton
                          size="sm"
                          variant="outline"
                          @click="approve(row)"
                        >
                          {{ t('lensAdmin.actions.approve') }}
                        </BaseButton>
                        <BaseButton
                          size="sm"
                          variant="ghost"
                          @click="reject(row)"
                        >
                          {{ t('lensAdmin.actions.reject') }}
                        </BaseButton>
                      </template>
                    </div>
                  </td>
                  <td class="table-cell">
                    <button
                      type="button"
                      class="text-left text-ink-600 transition-colors hover:text-primary-600 hover:underline"
                      :title="t('lensAdmin.detail.title')"
                      @click="openDetail(row)"
                    >
                      {{ row.workspace_path || EMPTY_VALUE }}
                    </button>
                  </td>
                  <td class="table-cell text-ink-600">
                    {{
                      t('lensAdmin.table.dirTaskSummary', {
                        dirs: row.available_dirs?.length || 0,
                        tasks: row.tasks?.length || 0
                      })
                    }}
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ formatDateTime(row.last_heartbeat_at) }}
                  </td>
                  <td class="table-cell">
                    <div class="flex items-center gap-2">
                      <BaseButton
                        size="sm"
                        variant="outline"
                        @click="startEdit(row)"
                      >
                        {{ t('common.edit') }}
                      </BaseButton>
                      <BaseButton
                        size="sm"
                        variant="danger"
                        @click="deleteTarget = row"
                      >
                        {{ t('common.delete') }}
                      </BaseButton>
                      <button
                        type="button"
                        class="rounded-md p-1.5 text-ink-400 transition-colors hover:bg-surface-sunken hover:text-ink-700"
                        :title="t('common.more')"
                        @click="openMenu(row, $event)"
                      >
                        <MoreVertical :size="16" :stroke-width="2" />
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <PaginationBar
            v-if="!loading"
            v-model:page-size="pageSize"
            :current-page="currentPage"
            :total="lensnodes.length"
            @page-size-change="handlePageSizeChange"
            @prev="goPrevPage"
            @next="goNextPage"
          />
        </div>
      </section>

      <!-- LensNode create / edit (name + onboarding compose) -->
      <LensNodeFormDrawer
        :show="showLensNodeDrawer"
        :mode="mode"
        :node="editingLensNode"
        :settings="globalSettings"
        @close="closeLensNodeDrawer"
        @done="load"
      />

      <!-- LensNode Detail Drawer (info + lazy directory tree) -->
      <LensNodeDetailDrawer
        :show="showDetailDrawer"
        :node="detailNode"
        @close="closeDetail"
      />

      <!-- Re-issue credential drawer (shows fresh compose) -->
      <BaseDrawer
        :show="showReissueDrawer"
        :title="t('lensAdmin.detail.reissue')"
        :subtitle="reissueNode?.name || ''"
        @close="closeReissue"
      >
        <LensNodeComposePanel
          v-if="reissueNode"
          :compose-text="reissueComposeText"
          :missing-labels="reissueMissingLabels"
        />
      </BaseDrawer>

      <!-- Row action menu, teleported so the table overflow can't clip it -->
      <Teleport to="body">
        <template v-if="openMenuRow">
          <div class="fixed inset-0 z-40" @click="closeMenu" />
          <div
            class="fixed z-50 w-36 rounded-md border border-line bg-surface py-1 shadow-lg"
            :style="menuStyle"
          >
            <button
              type="button"
              class="block w-full px-3 py-1.5 text-left text-sm text-ink-700 transition-colors hover:bg-surface-sunken"
              @click="reissue(openMenuRow)"
            >
              {{ t('lensAdmin.detail.reissue') }}
            </button>
            <button
              type="button"
              class="block w-full px-3 py-1.5 text-left text-sm text-danger-600 transition-colors hover:bg-danger-50"
              @click="revokeCredential(openMenuRow)"
            >
              {{ t('lensAdmin.actions.revokeToken') }}
            </button>
          </div>
        </template>
      </Teleport>

      <!-- Delete node confirmation -->
      <BaseModal
        :show="!!deleteTarget"
        :title="t('lensAdmin.deleteConfirm.title')"
        @close="deleteTarget = null"
      >
        <p class="text-sm text-ink-600">
          {{
            t('lensAdmin.deleteConfirm.message', {
              name: deleteTarget?.name
            })
          }}
        </p>
        <template #footer>
          <div class="flex flex-row-reverse gap-2">
            <BaseButton variant="danger" @click="confirmDeleteNode">
              {{ t('common.delete') }}
            </BaseButton>
            <BaseButton variant="outline" @click="deleteTarget = null">
              {{ t('common.cancel') }}
            </BaseButton>
          </div>
        </template>
      </BaseModal>
    </div>
  </AdminLayout>
</template>

<script setup>
import { MoreVertical } from '@lucide/vue'
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractErrorMessage } from '@/utils/api'
import AdminLayout from '@/admin/layout/AdminLayout.vue'
import {
  approveLensNode,
  deleteLensNode,
  issueLensNodeToken,
  listGlobalSettings,
  listLensNodes,
  rejectLensNode,
  revokeLensNodeToken
} from '@/api/lens'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'

import LensNodeComposePanel from './LensNodeComposePanel.vue'
import LensNodeDetailDrawer from './LensNodeDetailDrawer.vue'
import LensNodeFormDrawer from './LensNodeFormDrawer.vue'
import {
  EMPTY_VALUE,
  buildLensNodeCompose,
  compactUuid,
  lensNodeComposeSettings,
  normalizeList
} from './adminHelpers'
import { useShortDateTime } from './useShortDateTime'

const { t } = useI18n()
const { showSuccess, showError } = useToast()
const formatDateTime = useShortDateTime()

const lensnodes = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const globalSettings = ref([])
const loading = ref(false)
const mode = ref('create')
const showLensNodeDrawer = ref(false)
const editingLensNode = ref(null)
const showDetailDrawer = ref(false)
const detailNode = ref(null)
const openMenuRow = ref(null)
const menuStyle = ref({})
const deleteTarget = ref(null)
const showReissueDrawer = ref(false)
const reissueNode = ref(null)
const reissueToken = ref('')

const columns = computed(() =>
  [
    'lensnode',
    'runtimeStatus',
    'enrollment',
    'workspace',
    'dirsAndTasks',
    'heartbeat',
    'actions'
  ].map((column) => t(`lensAdmin.columns.${column}`))
)

const totalPages = computed(() =>
  Math.max(1, Math.ceil(lensnodes.value.length / pageSize.value))
)
const pagedLensNodes = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return lensnodes.value.slice(start, start + pageSize.value)
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

const composeConfig = computed(() =>
  lensNodeComposeSettings(globalSettings.value)
)

const reissueComposeText = computed(() =>
  buildLensNodeCompose({
    name: reissueNode.value?.name,
    token: reissueToken.value,
    ...composeConfig.value
  })
)

const reissueMissingLabels = computed(() =>
  composeConfig.value.serverUrl
    ? []
    : [t('lensAdmin.settings.publicBaseUrlTitle')]
)

async function load() {
  loading.value = true
  try {
    const [lensnodeRows, settingRows] = await Promise.all([
      listLensNodes(),
      listGlobalSettings()
    ])
    lensnodes.value = normalizeList(lensnodeRows)
    globalSettings.value = normalizeList(settingRows)
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.loadFailed')))
  } finally {
    loading.value = false
  }
}

function startCreate() {
  mode.value = 'create'
  editingLensNode.value = null
  showLensNodeDrawer.value = true
}

function startEdit(row) {
  mode.value = 'edit'
  editingLensNode.value = row
  showLensNodeDrawer.value = true
}

function closeLensNodeDrawer() {
  showLensNodeDrawer.value = false
  editingLensNode.value = null
}

function openDetail(row) {
  detailNode.value = row
  showDetailDrawer.value = true
}

function closeDetail() {
  showDetailDrawer.value = false
  detailNode.value = null
}

function closeMenu() {
  openMenuRow.value = null
  window.removeEventListener('scroll', closeMenu, true)
  window.removeEventListener('resize', closeMenu)
}

function openMenu(row, event) {
  if (openMenuRow.value?.uuid === row.uuid) {
    closeMenu()
    return
  }
  const rect = event.currentTarget.getBoundingClientRect()
  menuStyle.value = {
    top: `${rect.bottom + 4}px`,
    left: `${rect.right - 144}px`
  }
  openMenuRow.value = row
  // Close on scroll/resize so the fixed-position menu can't detach from the
  // trigger (the table scrolls horizontally under it).
  window.addEventListener('scroll', closeMenu, true)
  window.addEventListener('resize', closeMenu)
}

function confirmDeleteNode() {
  const row = deleteTarget.value
  deleteTarget.value = null
  if (row) {
    remove(row)
  }
}

function closeReissue() {
  showReissueDrawer.value = false
  reissueNode.value = null
  reissueToken.value = ''
}

async function reissue(row) {
  closeMenu()
  if (row.enrollment_status !== 'approved') {
    showError(t('lensAdmin.messages.approveBeforeToken'))
    return
  }
  try {
    const result = await issueLensNodeToken(row.uuid)
    reissueToken.value = result?.token || result?.auth_token || ''
    reissueNode.value = row
    showReissueDrawer.value = true
    await load()
  } catch (error) {
    showError(
      extractErrorMessage(error, t('lensAdmin.messages.tokenIssueFailed'))
    )
  }
}

async function revokeCredential(row) {
  closeMenu()
  try {
    await revokeLensNodeToken(row.uuid)
    showSuccess(t('lensAdmin.messages.tokenRevoked'))
    await load()
  } catch (error) {
    showError(
      extractErrorMessage(error, t('lensAdmin.messages.tokenRevokeFailed'))
    )
  }
}

async function remove(row) {
  try {
    await deleteLensNode(row.uuid)
    showSuccess(t('lensAdmin.messages.deleteSuccess'))
    await load()
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.deleteFailed')))
  }
}

async function approve(row) {
  try {
    await approveLensNode(row.uuid)
    showSuccess(t('lensAdmin.messages.approveSuccess'))
    await load()
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.approveFailed')))
  }
}

async function reject(row) {
  try {
    await rejectLensNode(row.uuid)
    showSuccess(t('lensAdmin.messages.rejectSuccess'))
    await load()
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.rejectFailed')))
  }
}

onMounted(load)
onUnmounted(closeMenu)
</script>

<style scoped>
.table-head {
  @apply border-b border-line px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-500;
}

.table-cell {
  @apply px-4 py-4 text-sm text-ink-700;
}
</style>
