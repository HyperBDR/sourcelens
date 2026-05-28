<template>
  <AdminLayout>
    <div class="w-full max-w-full p-6">
      <div class="mb-4">
        <h1 class="text-lg font-semibold text-gray-900">
          {{ t('management.roleManagement') }}
        </h1>
        <p class="mt-1 text-sm text-gray-500">
          {{ t('management.rolesSubtitle') }}
        </p>
      </div>

      <div class="rounded-lg border border-gray-200 bg-white shadow-sm">
        <div class="p-6">
          <div class="mb-6 flex flex-wrap items-center justify-between gap-3">
            <span class="text-sm text-gray-600">{{
              t('management.totalRoles', { count: totalCount })
            }}</span>
            <div class="flex items-center gap-2">
              <BaseButton
                variant="outline"
                size="sm"
                :loading="loading"
                @click="fetchRoles"
              >
                {{ t('common.refresh') }}
              </BaseButton>
              <BaseButton variant="primary" size="sm" @click="openCreateModal">
                {{ t('management.createRole') }}
              </BaseButton>
            </div>
          </div>

          <BaseLoading v-if="loading && !roles.length" />

          <div
            v-else-if="error"
            class="rounded-lg border border-gray-200 bg-gray-50 py-16 text-center"
          >
            <p class="text-sm font-medium text-red-600">{{ error }}</p>
          </div>

          <div
            v-else-if="!roles.length"
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
                  <th class="table-head">{{ t('management.roleName') }}</th>
                  <th class="table-head">
                    {{ t('management.visibleFeatures') }}
                  </th>
                  <th class="table-head">
                    {{ t('management.defaultPlatform') }}
                  </th>
                  <th class="table-head">
                    {{ t('management.groupUserCount') }}
                  </th>
                  <th class="table-head">{{ t('management.groupCount') }}</th>
                  <th class="table-head">{{ t('management.isActive') }}</th>
                  <th class="table-head">{{ t('common.actions') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-100 bg-white">
                <tr
                  v-for="role in roles"
                  :key="role.id"
                  class="transition-colors duration-150 hover:bg-gray-50"
                >
                  <td class="table-cell text-gray-900">{{ role.id }}</td>
                  <td class="table-cell font-medium text-gray-900">
                    {{ role.name }}
                  </td>
                  <td class="table-cell text-gray-500">
                    {{ formatFeatures(role.visible_features) }}
                  </td>
                  <td class="table-cell text-gray-500">
                    {{ formatPlatform(role.preferred_platform) }}
                  </td>
                  <td class="table-cell text-gray-500">
                    {{ role.user_count ?? 0 }}
                  </td>
                  <td class="table-cell text-gray-500">
                    {{ role.group_count ?? 0 }}
                  </td>
                  <td class="table-cell">
                    <span
                      :class="
                        role.is_active ? 'text-green-600' : 'text-gray-400'
                      "
                    >
                      {{ role.is_active ? t('common.yes') : t('common.no') }}
                    </span>
                  </td>
                  <td class="table-cell">
                    <BaseButton
                      variant="outline"
                      size="sm"
                      @click="openEditModal(role)"
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
        <form @submit.prevent="submitRole" class="space-y-4">
          <p v-if="submitError" class="text-sm text-red-600">
            {{ submitError }}
          </p>
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">{{
              t('management.roleName')
            }}</label>
            <input v-model="form.name" type="text" class="form-input" />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">{{
              t('management.visibleFeatures')
            }}</label>
            <div
              class="space-y-2 rounded-md border border-gray-300 bg-white p-3"
            >
              <label
                v-for="platform in platformOptions"
                :key="platform.key"
                class="flex cursor-pointer items-start gap-3 rounded px-2 py-1 hover:bg-gray-50"
              >
                <input
                  v-model="form.visible_features"
                  type="checkbox"
                  :value="platform.key"
                  class="mt-0.5 h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
                />
                <span class="text-sm text-gray-700">{{ platform.label }}</span>
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
              <option value="">{{ t('management.noDefaultPlatform') }}</option>
              <option
                v-for="platform in selectedPlatformOptions"
                :key="platform.key"
                :value="platform.key"
              >
                {{ platform.label }}
              </option>
            </select>
          </div>
          <div class="flex items-center gap-3">
            <input
              v-model="form.is_active"
              type="checkbox"
              id="role-is-active"
              class="h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
            />
            <label
              for="role-is-active"
              class="cursor-pointer text-sm font-medium text-gray-700"
            >
              {{ t('management.isActive') }}
            </label>
          </div>
        </form>
        <template #footer>
          <div class="flex flex-row-reverse gap-2">
            <BaseButton
              variant="primary"
              :loading="submitLoading"
              @click="submitRole"
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
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AdminLayout from '@/admin/layout/AdminLayout.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import { managementApi } from '@/admin/api'
import { FEATURE_DEFINITIONS } from '@/utils/platformAccess'

const { t } = useI18n()

const roles = ref([])
const loading = ref(false)
const error = ref(null)
const currentPage = ref(1)
const pageSize = ref(20)
const totalCount = ref(0)

const showModal = ref(false)
const mode = ref('create')
const editingRoleId = ref(null)
const submitLoading = ref(false)
const submitError = ref(null)
const form = ref({
  name: '',
  visible_features: [],
  preferred_platform: '',
  is_active: true
})

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
    ? t('management.createRole')
    : t('management.editRole')
)

const platformOptions = computed(() =>
  FEATURE_DEFINITIONS.map((item) => ({
    key: item.key,
    label: t(item.labelKey)
  }))
)

const selectedPlatformOptions = computed(() =>
  platformOptions.value.filter((item) =>
    form.value.visible_features.includes(item.key)
  )
)

watch(
  () => form.value.visible_features,
  (visibleFeatures) => {
    if (!visibleFeatures.includes(form.value.preferred_platform)) {
      form.value.preferred_platform = ''
    }
  }
)

function formatFeatures(items) {
  if (!Array.isArray(items) || !items.length) return '—'
  return items
    .map(
      (item) =>
        platformOptions.value.find((platform) => platform.key === item)
          ?.label || item
    )
    .join(', ')
}

function formatPlatform(value) {
  const match = platformOptions.value.find((item) => item.key === value)
  return match?.label || '—'
}

function closeModal() {
  showModal.value = false
  editingRoleId.value = null
  submitError.value = null
  submitLoading.value = false
  form.value = {
    name: '',
    visible_features: [],
    preferred_platform: '',
    is_active: true
  }
}

function openCreateModal() {
  mode.value = 'create'
  closeModal()
  mode.value = 'create'
  showModal.value = true
}

function openEditModal(role) {
  mode.value = 'edit'
  editingRoleId.value = role.id
  form.value = {
    name: role.name || '',
    visible_features: Array.isArray(role.visible_features)
      ? [...role.visible_features]
      : [],
    preferred_platform: role.preferred_platform || '',
    is_active: role.is_active !== false
  }
  showModal.value = true
}

async function submitRole() {
  submitError.value = null
  const name = (form.value.name || '').trim()
  if (!name) {
    submitError.value = t('management.roleNameRequired')
    return
  }

  submitLoading.value = true
  try {
    const payload = {
      name,
      visible_features: Array.isArray(form.value.visible_features)
        ? form.value.visible_features
        : [],
      preferred_platform: form.value.preferred_platform || '',
      is_active: !!form.value.is_active
    }
    if (mode.value === 'create') {
      await managementApi.createRole(payload)
    } else {
      await managementApi.updateRole(editingRoleId.value, payload)
    }
    closeModal()
    await fetchRoles()
  } catch (e) {
    if (e?.response?.data?.code === 'name_taken') {
      submitError.value = t('management.roleNameTaken')
    } else {
      submitError.value =
        e?.response?.data?.detail || e?.message || t('common.error')
    }
  } finally {
    submitLoading.value = false
  }
}

async function fetchRoles() {
  loading.value = true
  error.value = null
  try {
    const data = await managementApi.getRoles({
      page: currentPage.value,
      page_size: pageSize.value
    })
    roles.value = Array.isArray(data) ? data : (data?.results ?? [])
    totalCount.value = Array.isArray(data)
      ? data.length
      : Number(data?.count ?? roles.value.length)
  } catch (e) {
    roles.value = []
    totalCount.value = 0
    error.value = e?.response?.data?.detail || e?.message || t('common.error')
  } finally {
    loading.value = false
  }
}

function handlePageSizeChange() {
  currentPage.value = 1
  fetchRoles()
}

function goPrevPage() {
  if (currentPage.value <= 1) return
  currentPage.value -= 1
  fetchRoles()
}

function goNextPage() {
  if (currentPage.value >= totalPages.value) return
  currentPage.value += 1
  fetchRoles()
}

onMounted(() => {
  fetchRoles()
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
