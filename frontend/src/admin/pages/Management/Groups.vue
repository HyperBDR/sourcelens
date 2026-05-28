<template>
  <AdminLayout>
    <div class="w-full max-w-full p-6">
      <div class="mb-4">
        <h1 class="text-lg font-semibold text-gray-900">
          {{ t('management.groupManagement') }}
        </h1>
        <p class="mt-1 text-sm text-gray-500">
          {{ t('management.groupsSubtitle') }}
        </p>
      </div>

      <div class="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div class="p-6">
          <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
            <span class="text-sm text-gray-600">{{
              t('management.totalGroups', { count: totalCount })
            }}</span>
            <div class="flex items-center gap-2">
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

          <BaseLoading v-if="loading && !groups.length" />

          <div
            v-else-if="error"
            class="rounded-lg border border-gray-200 bg-gray-50 py-16 text-center"
          >
            <p class="text-sm font-medium text-red-600">{{ error }}</p>
          </div>

          <div
            v-else-if="!groups.length"
            class="rounded-lg border border-gray-200 bg-gray-50 py-16 text-center"
          >
            <p class="text-sm font-medium text-gray-600">
              {{ t('common.noData') }}
            </p>
          </div>

          <div
            v-else
            class="relative overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm"
          >
            <table class="min-w-full divide-y divide-gray-200">
              <thead class="bg-gradient-to-r from-gray-50 to-gray-100">
                <tr>
                  <th class="table-head">ID</th>
                  <th class="table-head">{{ t('management.groupName') }}</th>
                  <th class="table-head">
                    {{ t('management.groupUserCount') }}
                  </th>
                  <th class="table-head">{{ t('management.roles') }}</th>
                  <th class="table-head">
                    {{ t('management.permissionCount') }}
                  </th>
                  <th class="table-head">{{ t('common.actions') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100 bg-white">
                <tr
                  v-for="group in groups"
                  :key="group.id"
                  class="transition-colors duration-150 hover:bg-gray-50"
                >
                  <td class="table-cell text-gray-900">{{ group.id }}</td>
                  <td class="table-cell font-medium text-gray-900">
                    {{ group.name }}
                  </td>
                  <td class="table-cell text-gray-500">
                    {{ group.user_count ?? 0 }}
                  </td>
                  <td class="table-cell text-gray-500">
                    {{ joinNames(group.roles) }}
                  </td>
                  <td class="table-cell text-gray-500">
                    {{ group.permission_count ?? 0 }}
                  </td>
                  <td class="table-cell">
                    <BaseButton
                      variant="outline"
                      size="sm"
                      @click="openEditModal(group)"
                    >
                      {{ t('common.edit') }}
                    </BaseButton>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div
            v-if="!loading && totalCount > 0"
            class="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-gray-200 pt-4"
          >
            <p class="text-sm text-gray-600">
              {{ t('common.pagination.showing', paginationShowing) }}
            </p>
            <div class="flex items-center gap-2">
              <label class="text-sm text-gray-600"
                >{{ t('common.pagination.itemsPerPage') }}:</label
              >
              <select
                v-model.number="pageSize"
                class="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500"
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
                @click="goPrevPage"
              >
                {{ t('common.pagination.previous') }}
              </BaseButton>
              <BaseButton
                variant="outline"
                size="sm"
                :disabled="currentPage >= totalPages"
                @click="goNextPage"
              >
                {{ t('common.pagination.next') }}
              </BaseButton>
            </div>
          </div>
        </div>
      </div>

      <BaseModal :show="showModal" :title="modalTitle" @close="closeModal">
        <form @submit.prevent="submitGroup" class="space-y-4">
          <p v-if="submitError" class="text-sm text-red-600">
            {{ submitError }}
          </p>
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">{{
              t('management.groupName')
            }}</label>
            <input v-model="form.name" type="text" class="form-input" />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">{{
              t('management.selectRoles')
            }}</label>
            <div
              class="max-h-40 space-y-2 overflow-y-auto rounded-md border border-gray-300 bg-white p-2"
            >
              <label
                v-for="role in roleOptions"
                :key="role.id"
                class="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-gray-50"
              >
                <input
                  v-model="form.role_ids"
                  type="checkbox"
                  :value="role.id"
                  class="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span class="text-sm text-gray-700">{{ role.name }}</span>
              </label>
            </div>
          </div>
        </form>
        <template #footer>
          <div class="flex flex-row-reverse gap-2">
            <BaseButton
              variant="primary"
              :loading="submitLoading"
              @click="submitGroup"
            >
              {{ t('common.confirm') }}
            </BaseButton>
            <BaseButton variant="outline" @click="closeModal">
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
import BaseModal from '@/components/ui/BaseModal.vue'
import { managementApi } from '@/admin/api'

const { t } = useI18n()

const groups = ref([])
const loading = ref(false)
const error = ref(null)
const currentPage = ref(1)
const pageSize = ref(20)
const totalCount = ref(0)

const roleOptions = ref([])

const showModal = ref(false)
const mode = ref('create')
const editingGroupId = ref(null)
const submitLoading = ref(false)
const submitError = ref(null)
const form = ref({ name: '', role_ids: [] })

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

function joinNames(items) {
  return Array.isArray(items) && items.length
    ? items.map((item) => item.name).join(', ')
    : '—'
}

function closeModal() {
  showModal.value = false
  editingGroupId.value = null
  submitError.value = null
  submitLoading.value = false
  form.value = { name: '', role_ids: [] }
}

function openCreateModal() {
  mode.value = 'create'
  form.value = { name: '', role_ids: [] }
  showModal.value = true
}

function openEditModal(group) {
  mode.value = 'edit'
  editingGroupId.value = group.id
  form.value = {
    name: group.name || '',
    role_ids: Array.isArray(group.roles)
      ? group.roles.map((item) => item.id)
      : []
  }
  showModal.value = true
}

async function loadRoleOptions() {
  try {
    const data = await managementApi.getRoles({ page: 1, page_size: 1000 })
    roleOptions.value = Array.isArray(data) ? data : (data?.results ?? [])
  } catch {
    roleOptions.value = []
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
      role_ids: Array.isArray(form.value.role_ids) ? form.value.role_ids : []
    }
    if (mode.value === 'create') {
      await managementApi.createGroup(payload)
    } else {
      await managementApi.updateGroup(editingGroupId.value, payload)
    }
    closeModal()
    await fetchGroups()
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
  await Promise.all([fetchGroups(), loadRoleOptions()])
})
</script>

<style scoped>
.table-head {
  @apply border-b border-gray-200 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-700;
}

.table-cell {
  @apply px-4 py-4 text-sm;
}

.form-input {
  @apply w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500;
}
</style>
