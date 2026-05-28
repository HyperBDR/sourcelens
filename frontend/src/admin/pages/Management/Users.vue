<template>
  <AdminLayout>
    <div class="w-full max-w-full p-6">
      <div class="mb-4">
        <h1 class="text-lg font-semibold text-gray-900">
          {{ t('management.userManagement') }}
        </h1>
        <p class="mt-1 text-sm text-gray-500">
          {{ t('management.usersSubtitle') }}
        </p>
      </div>

      <div class="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div class="p-6">
          <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
            <span class="text-sm text-gray-600">{{
              t('management.totalUsers', { count: totalCount })
            }}</span>
            <div class="flex items-center gap-2">
              <BaseButton
                variant="outline"
                size="sm"
                :loading="loading"
                @click="fetchUsers"
              >
                {{ t('common.refresh') }}
              </BaseButton>
              <BaseButton variant="primary" size="sm" @click="openCreateModal">
                {{ t('management.createUser') }}
              </BaseButton>
            </div>
          </div>

          <BaseLoading v-if="loading && !users.length" />

          <div
            v-else-if="error"
            class="rounded-lg border border-gray-200 bg-gray-50 py-16 text-center"
          >
            <p class="text-sm font-medium text-red-600">{{ error }}</p>
          </div>

          <div
            v-else-if="!users.length"
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
                  <th class="table-head">{{ t('dashboard.username') }}</th>
                  <th class="table-head">{{ t('dashboard.email') }}</th>
                  <th class="table-head">{{ t('management.groups') }}</th>
                  <th class="table-head">{{ t('management.roles') }}</th>
                  <th class="table-head">
                    {{ t('management.defaultPlatform') }}
                  </th>
                  <th class="table-head">{{ t('dashboard.isStaff') }}</th>
                  <th class="table-head">{{ t('management.isActive') }}</th>
                  <th class="table-head">{{ t('management.dateJoined') }}</th>
                  <th class="table-head">{{ t('common.actions') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100 bg-white">
                <tr
                  v-for="user in users"
                  :key="user.id"
                  class="transition-colors duration-150 hover:bg-gray-50"
                >
                  <td class="table-cell text-gray-900">{{ user.id }}</td>
                  <td class="table-cell">
                    <div class="font-medium text-gray-900">
                      {{ user.username }}
                    </div>
                    <div class="text-xs text-gray-500">
                      {{ user.display_name || '—' }}
                    </div>
                  </td>
                  <td class="table-cell text-gray-500">
                    {{ user.email || '—' }}
                  </td>
                  <td class="table-cell text-gray-500">
                    {{ joinNames(user.groups) }}
                  </td>
                  <td class="table-cell text-gray-500">
                    {{ joinNames(user.effective_roles || user.roles) }}
                  </td>
                  <td class="table-cell text-gray-500">
                    {{
                      formatPlatform(
                        user.preferred_platform ||
                          user.access_profile?.preferred_platform
                      )
                    }}
                  </td>
                  <td class="table-cell">
                    <span
                      :class="
                        user.is_staff ? 'text-indigo-600' : 'text-gray-400'
                      "
                    >
                      {{ user.is_staff ? t('common.yes') : t('common.no') }}
                    </span>
                  </td>
                  <td class="table-cell">
                    <span
                      :class="
                        user.is_active !== false
                          ? 'text-green-600'
                          : 'text-gray-400'
                      "
                    >
                      {{
                        user.is_active !== false
                          ? t('common.yes')
                          : t('common.no')
                      }}
                    </span>
                  </td>
                  <td class="table-cell text-gray-500">
                    {{ formatDate(user.date_joined) }}
                  </td>
                  <td class="table-cell">
                    <BaseButton
                      variant="outline"
                      size="sm"
                      @click="openEditModal(user)"
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
        <form @submit.prevent="submitUser" class="space-y-4">
          <p v-if="submitError" class="text-sm text-red-600">
            {{ submitError }}
          </p>
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">{{
              t('dashboard.username')
            }}</label>
            <input v-model="form.username" type="text" class="form-input" />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">{{
              t('dashboard.email')
            }}</label>
            <input v-model="form.email" type="email" class="form-input" />
          </div>
          <div v-if="mode === 'create'">
            <label class="mb-1 block text-sm font-medium text-gray-700">{{
              t('password.reset.newPassword')
            }}</label>
            <input v-model="form.password" type="password" class="form-input" />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">{{
              t('management.selectGroups')
            }}</label>
            <div
              class="max-h-32 space-y-2 overflow-y-auto rounded-md border border-gray-300 bg-white p-2"
            >
              <label
                v-for="group in groupOptions"
                :key="group.id"
                class="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-gray-50"
              >
                <input
                  v-model="form.group_ids"
                  type="checkbox"
                  :value="group.id"
                  class="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span class="text-sm text-gray-700">{{ group.name }}</span>
              </label>
            </div>
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
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">{{
              t('management.defaultPlatform')
            }}</label>
            <select
              v-model="form.preferred_platform"
              class="form-input bg-white"
            >
              <option value="">
                {{ t('management.followRolePreference') }}
              </option>
              <option
                v-for="platform in platformOptions"
                :key="platform.key"
                :value="platform.key"
              >
                {{ platform.label }}
              </option>
            </select>
          </div>
          <div class="grid gap-4 md:grid-cols-2">
            <div class="flex items-center gap-3">
              <input
                v-model="form.is_staff"
                type="checkbox"
                id="user-is-staff"
                class="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <label
                for="user-is-staff"
                class="cursor-pointer text-sm font-medium text-gray-700"
              >
                {{ t('dashboard.isStaff') }}
              </label>
            </div>
            <div class="flex items-center gap-3">
              <input
                v-model="form.is_active"
                type="checkbox"
                id="user-is-active"
                class="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <label
                for="user-is-active"
                class="cursor-pointer text-sm font-medium text-gray-700"
              >
                {{ t('management.isActive') }}
              </label>
            </div>
          </div>
        </form>
        <template #footer>
          <div class="flex flex-row-reverse gap-2">
            <BaseButton
              variant="primary"
              :loading="submitLoading"
              @click="submitUser"
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
import { FEATURE_DEFINITIONS } from '@/utils/platformAccess'

const { t } = useI18n()

const users = ref([])
const loading = ref(false)
const error = ref(null)
const currentPage = ref(1)
const pageSize = ref(20)
const totalCount = ref(0)

const showModal = ref(false)
const mode = ref('create')
const editingUserId = ref(null)
const submitLoading = ref(false)
const submitError = ref(null)

const groupOptions = ref([])
const roleOptions = ref([])

const createEmptyForm = () => ({
  username: '',
  email: '',
  password: '',
  is_staff: false,
  is_active: true,
  group_ids: [],
  role_ids: [],
  preferred_platform: ''
})

const form = ref(createEmptyForm())

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
    ? t('management.createUser')
    : t('management.editUser')
)

const platformOptions = computed(() =>
  FEATURE_DEFINITIONS.map((item) => ({
    key: item.key,
    label: t(item.labelKey)
  }))
)

function joinNames(items) {
  return Array.isArray(items) && items.length
    ? items.map((item) => item.name).join(', ')
    : '—'
}

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

function formatPlatform(value) {
  const match = platformOptions.value.find((item) => item.key === value)
  return match?.label || '—'
}

function closeModal() {
  showModal.value = false
  submitError.value = null
  submitLoading.value = false
  editingUserId.value = null
  form.value = createEmptyForm()
}

function openCreateModal() {
  mode.value = 'create'
  form.value = createEmptyForm()
  showModal.value = true
}

function openEditModal(user) {
  mode.value = 'edit'
  editingUserId.value = user.id
  form.value = {
    username: user.username || '',
    email: user.email || '',
    password: '',
    is_staff: !!user.is_staff,
    is_active: user.is_active !== false,
    group_ids: Array.isArray(user.groups)
      ? user.groups.map((item) => item.id)
      : [],
    role_ids: Array.isArray(user.roles)
      ? user.roles.map((item) => item.id)
      : [],
    preferred_platform: user.preferred_platform || ''
  }
  showModal.value = true
}

async function loadOptions() {
  try {
    const [groupsData, rolesData] = await Promise.all([
      managementApi.getGroups({ page: 1, page_size: 1000 }),
      managementApi.getRoles({ page: 1, page_size: 1000 })
    ])
    groupOptions.value = Array.isArray(groupsData)
      ? groupsData
      : (groupsData?.results ?? [])
    roleOptions.value = Array.isArray(rolesData)
      ? rolesData
      : (rolesData?.results ?? [])
  } catch {
    groupOptions.value = []
    roleOptions.value = []
  }
}

async function submitUser() {
  submitError.value = null
  const payload = {
    username: (form.value.username || '').trim(),
    email: (form.value.email || '').trim(),
    is_staff: !!form.value.is_staff,
    is_active: !!form.value.is_active,
    group_ids: Array.isArray(form.value.group_ids) ? form.value.group_ids : [],
    role_ids: Array.isArray(form.value.role_ids) ? form.value.role_ids : [],
    preferred_platform: form.value.preferred_platform || ''
  }

  if (!payload.username) {
    submitError.value = t('management.usernameRequired')
    return
  }

  if (mode.value === 'create') {
    payload.password = (form.value.password || '').trim()
    if (!payload.password) {
      submitError.value = t('management.passwordRequired')
      return
    }
  }

  submitLoading.value = true
  try {
    if (mode.value === 'create') {
      await managementApi.createUser(payload)
    } else {
      await managementApi.updateUser(editingUserId.value, payload)
    }
    closeModal()
    await fetchUsers()
  } catch (e) {
    const detail = e?.response?.data?.detail
    if (e?.response?.data?.code === 'username_taken') {
      submitError.value = t('management.usernameTaken')
    } else if (e?.response?.data?.code === 'email_taken') {
      submitError.value = t('management.emailTaken')
    } else {
      submitError.value =
        typeof detail === 'string' ? detail : t('common.error')
    }
  } finally {
    submitLoading.value = false
  }
}

async function fetchUsers() {
  loading.value = true
  error.value = null
  try {
    const data = await managementApi.getUsers({
      page: currentPage.value,
      page_size: pageSize.value
    })
    users.value = Array.isArray(data) ? data : (data?.results ?? [])
    totalCount.value = Array.isArray(data)
      ? data.length
      : Number(data?.count ?? users.value.length)
  } catch (e) {
    users.value = []
    totalCount.value = 0
    error.value = e?.response?.data?.detail || e?.message || t('common.error')
  } finally {
    loading.value = false
  }
}

function handlePageSizeChange() {
  currentPage.value = 1
  fetchUsers()
}

function goPrevPage() {
  if (currentPage.value <= 1) return
  currentPage.value -= 1
  fetchUsers()
}

function goNextPage() {
  if (currentPage.value >= totalPages.value) return
  currentPage.value += 1
  fetchUsers()
}

onMounted(async () => {
  await Promise.all([fetchUsers(), loadOptions()])
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
