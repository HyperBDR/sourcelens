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
            <h1 class="text-xl font-semibold text-ink-900">
              {{ t('management.groupManagement') }}
            </h1>
            <p class="max-w-3xl text-sm leading-6 text-ink-500">
              {{ t('management.groupsSubtitle') }}
            </p>
            <div class="flex flex-wrap items-center gap-2 text-xs text-ink-500">
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1"
              >
                {{ t('management.totalGroups', { count: totalCount }) }}
              </span>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <BaseButton
              variant="outline"
              size="sm"
              :loading="loading"
              @click="fetchGroups"
            >
              {{ t('common.refresh') }}
            </BaseButton>
            <BaseButton variant="primary" size="sm" @click="openCreateModal">
              {{ t('management.createGroup') }}
            </BaseButton>
          </div>
        </div>

        <div class="px-5 py-4">
          <BaseLoading v-if="loading && !groups.length" />

          <div
            v-else-if="error"
            class="rounded-lg border border-line bg-surface-sunken py-16 text-center"
          >
            <p class="text-sm font-medium text-danger-700">{{ error }}</p>
          </div>

          <div
            v-else-if="!groups.length"
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
                  <th class="table-head">ID</th>
                  <th class="table-head">{{ t('management.groupName') }}</th>
                  <th class="table-head">
                    {{ t('management.groupUserCount') }}
                  </th>
                  <th class="table-head">
                    {{ t('management.permissionCount') }}
                  </th>
                  <th class="table-head">{{ t('common.actions') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line bg-surface">
                <tr
                  v-for="group in groups"
                  :key="group.id"
                  class="transition-colors hover:bg-line-soft"
                >
                  <td class="table-cell font-mono text-ink-500">
                    {{ group.id }}
                  </td>
                  <td class="table-cell font-medium text-ink-900">
                    {{ group.name }}
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ group.user_count ?? 0 }}
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ group.permission_count ?? 0 }}
                  </td>
                  <td class="table-cell">
                    <div class="flex items-center gap-2">
                      <BaseButton
                        variant="outline"
                        size="sm"
                        @click="openEditModal(group)"
                      >
                        {{ t('common.edit') }}
                      </BaseButton>
                      <BaseButton
                        variant="danger"
                        size="sm"
                        @click="askDelete(group)"
                      >
                        {{ t('common.delete') }}
                      </BaseButton>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div
            v-if="!loading && totalCount > 0"
            class="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-4"
          >
            <p class="text-sm text-ink-500">
              {{ t('common.pagination.showing', paginationShowing) }}
            </p>
            <div class="flex items-center gap-2">
              <label class="whitespace-nowrap text-sm text-ink-500"
                >{{ t('common.pagination.itemsPerPage') }}:</label
              >
              <select
                v-model.number="pageSize"
                class="rounded-lg border border-line bg-surface px-2 py-1.5 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                @change="handlePageSizeChange"
              >
                <option :value="10">10</option>
                <option :value="20">20</option>
                <option :value="50">50</option>
                <option :value="100">100</option>
              </select>
              <BaseButton
                variant="outline"
                size="sm"
                :disabled="currentPage <= 1"
                :title="t('common.pagination.previous')"
                @click="goPrevPage"
              >
                <svg
                  class="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M15 19l-7-7 7-7"
                  />
                </svg>
                <span class="sr-only">{{
                  t('common.pagination.previous')
                }}</span>
              </BaseButton>
              <BaseButton
                variant="outline"
                size="sm"
                :disabled="currentPage >= totalPages"
                :title="t('common.pagination.next')"
                @click="goNextPage"
              >
                <svg
                  class="h-4 w-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    stroke-linecap="round"
                    stroke-linejoin="round"
                    stroke-width="2"
                    d="M9 5l7 7-7 7"
                  />
                </svg>
                <span class="sr-only">{{ t('common.pagination.next') }}</span>
              </BaseButton>
            </div>
          </div>
        </div>
      </section>

      <BaseDrawer
        :show="showModal"
        :title="modalTitle"
        :subtitle="form.name || ''"
        @close="closeModal"
      >
        <form id="group-form" class="space-y-4" @submit.prevent="submitGroup">
          <p v-if="submitError" class="text-sm text-danger-700">
            {{ submitError }}
          </p>
          <div>
            <label class="mb-1 block text-sm font-medium text-ink-700">{{
              t('management.groupName')
            }}</label>
            <input v-model="form.name" type="text" class="form-input" />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-ink-700">{{
              t('management.members')
            }}</label>
            <div
              class="max-h-60 space-y-1 overflow-y-auto rounded-lg border border-line bg-surface-sunken p-2"
            >
              <label
                v-for="user in userOptions"
                :key="user.id"
                class="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm text-ink-700 hover:bg-surface"
              >
                <input
                  v-model="form.user_ids"
                  type="checkbox"
                  :value="user.id"
                  class="h-4 w-4 rounded border-line text-brand-600 focus:ring-brand-500"
                />
                <span class="font-medium">{{
                  user.display_name || user.username
                }}</span>
                <span v-if="user.email" class="text-xs text-ink-400">{{
                  user.email
                }}</span>
              </label>
              <p
                v-if="!userOptions.length"
                class="px-2 py-1 text-xs text-ink-400"
              >
                {{ t('common.noData') }}
              </p>
            </div>
          </div>
        </form>
        <template #footer>
          <div class="flex flex-row-reverse gap-2">
            <BaseButton
              variant="primary"
              :loading="submitLoading"
              type="submit"
              form="group-form"
            >
              {{ t('common.confirm') }}
            </BaseButton>
            <BaseButton variant="outline" @click="closeModal">
              {{ t('common.cancel') }}
            </BaseButton>
          </div>
        </template>
      </BaseDrawer>

      <BaseModal
        :show="!!deleteTarget"
        :title="t('management.deleteGroup')"
        @close="deleteTarget = null"
      >
        <p class="text-sm leading-6 text-ink-700">
          {{
            t('management.deleteGroupConfirm', {
              name: deleteTarget?.name,
              members: deleteTarget?.user_count ?? 0,
              assistants: deleteTarget?.assistant_grant_count ?? 0
            })
          }}
        </p>
        <template #footer>
          <div class="flex flex-row-reverse gap-2">
            <BaseButton
              variant="danger"
              :loading="deletingId === deleteTarget?.id"
              @click="confirmDelete"
            >
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
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AdminLayout from '@/admin/layout/AdminLayout.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { useToast } from '@/composables/useToast'
import { managementApi } from '@/admin/api'

const { t } = useI18n()
const { showSuccess, showError } = useToast()

const groups = ref([])
const loading = ref(false)
const error = ref(null)
const currentPage = ref(1)
const pageSize = ref(20)
const totalCount = ref(0)
const userOptions = ref([])
const deleteTarget = ref(null)
const deletingId = ref(null)

const showModal = ref(false)
const mode = ref('create')
const editingGroupId = ref(null)
const submitLoading = ref(false)
const submitError = ref(null)
const form = ref({ name: '', user_ids: [] })

const totalPages = computed(() =>
  totalCount.value > 0 ? Math.ceil(totalCount.value / pageSize.value) : 1
)

const paginationShowing = computed(() => ({
  from:
    totalCount.value === 0 ? 0 : (currentPage.value - 1) * pageSize.value + 1,
  to: Math.min(currentPage.value * pageSize.value, totalCount.value),
  total: totalCount.value
}))

const modalTitle = computed(() =>
  mode.value === 'create'
    ? t('management.createGroup')
    : t('management.editGroup')
)

function closeModal() {
  showModal.value = false
  editingGroupId.value = null
  submitError.value = null
  submitLoading.value = false
  form.value = { name: '', user_ids: [] }
}

function openCreateModal() {
  mode.value = 'create'
  form.value = { name: '', user_ids: [] }
  showModal.value = true
}

function memberIdsForGroup(groupId) {
  return userOptions.value
    .filter((user) => (user.groups || []).some((group) => group.id === groupId))
    .map((user) => user.id)
}

function openEditModal(group) {
  mode.value = 'edit'
  editingGroupId.value = group.id
  form.value = {
    name: group.name || '',
    user_ids: memberIdsForGroup(group.id)
  }
  showModal.value = true
}

async function loadUsers() {
  try {
    const data = await managementApi.getUsers({ page: 1, page_size: 1000 })
    userOptions.value = Array.isArray(data) ? data : (data?.results ?? [])
  } catch {
    userOptions.value = []
  }
}

function askDelete(group) {
  deleteTarget.value = group
}

async function confirmDelete() {
  const group = deleteTarget.value
  if (!group) return
  deletingId.value = group.id
  try {
    await managementApi.deleteGroup(group.id)
    deleteTarget.value = null
    showSuccess(t('management.groupDeleted'))
    await Promise.all([fetchGroups(), loadUsers()])
  } catch (e) {
    showError(e?.response?.data?.detail || e?.message || t('common.error'))
  } finally {
    deletingId.value = null
  }
}

async function submitGroup() {
  submitError.value = null
  const name = (form.value.name || '').trim()
  if (!name) {
    submitError.value = t('management.groupNameRequired')
    return
  }

  submitLoading.value = true
  try {
    const payload = {
      name,
      user_ids: Array.isArray(form.value.user_ids) ? form.value.user_ids : []
    }
    if (mode.value === 'create') {
      await managementApi.createGroup(payload)
    } else {
      await managementApi.updateGroup(editingGroupId.value, payload)
    }
    closeModal()
    await Promise.all([fetchGroups(), loadUsers()])
  } catch (e) {
    if (e?.response?.data?.code === 'name_taken') {
      submitError.value = t('management.groupNameTaken')
    } else {
      submitError.value =
        e?.response?.data?.detail || e?.message || t('common.error')
    }
  } finally {
    submitLoading.value = false
  }
}

async function fetchGroups() {
  loading.value = true
  error.value = null
  try {
    const data = await managementApi.getGroups({
      page: currentPage.value,
      page_size: pageSize.value
    })
    groups.value = Array.isArray(data) ? data : (data?.results ?? [])
    totalCount.value = Array.isArray(data)
      ? data.length
      : Number(data?.count ?? groups.value.length)
  } catch (e) {
    groups.value = []
    totalCount.value = 0
    error.value = e?.response?.data?.detail || e?.message || t('common.error')
  } finally {
    loading.value = false
  }
}

function handlePageSizeChange() {
  currentPage.value = 1
  fetchGroups()
}

function goPrevPage() {
  if (currentPage.value <= 1) return
  currentPage.value -= 1
  fetchGroups()
}

function goNextPage() {
  if (currentPage.value >= totalPages.value) return
  currentPage.value += 1
  fetchGroups()
}

onMounted(async () => {
  await Promise.all([fetchGroups(), loadUsers()])
})
</script>

<style scoped>
.table-head {
  @apply border-b border-line px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-500;
}

.table-cell {
  @apply px-4 py-4 text-sm text-ink-700;
}

.form-input {
  @apply w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}
</style>
