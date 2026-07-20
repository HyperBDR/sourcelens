<template>
  <AdminLayout>
    <div class="flex h-full min-h-0 max-w-full flex-col gap-4 py-4">
      <section
        class="flex max-h-full min-h-0 w-full flex-col overflow-hidden rounded-lg border border-line bg-surface shadow-sm"
      >
        <div
          class="flex flex-shrink-0 flex-col gap-4 border-b border-line px-5 py-4 lg:flex-row lg:items-start lg:justify-between"
        >
          <div class="min-w-0 space-y-2">
            <h1 class="text-xl font-semibold text-ink-900">
              {{ t('management.userManagement') }}
            </h1>
            <p class="max-w-3xl text-sm leading-6 text-ink-500">
              {{ t('management.usersSubtitle') }}
            </p>
            <div class="flex flex-wrap items-center gap-2 text-xs text-ink-500">
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1"
              >
                {{ t('management.totalUsers', { count: totalCount }) }}
              </span>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
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

        <div class="flex min-h-0 flex-1 flex-col px-5 py-4">
          <form
            class="mb-4 flex flex-shrink-0 flex-wrap items-end gap-3"
            @submit.prevent="applyExactFilters"
          >
            <label class="min-w-0 flex-1 sm:max-w-xs">
              <span class="mb-1 block text-sm font-medium text-ink-700">
                {{ t('management.usernameFilter') }}
              </span>
              <input
                v-model="usernameFilterInput"
                data-testid="username-filter-input"
                type="text"
                class="form-input"
                :placeholder="t('management.usernameFilterPlaceholder')"
              />
            </label>
            <label class="min-w-0 flex-1 sm:max-w-xs">
              <span class="mb-1 block text-sm font-medium text-ink-700">
                {{ t('management.emailFilter') }}
              </span>
              <input
                v-model="emailFilterInput"
                data-testid="email-filter-input"
                type="email"
                class="form-input"
                :placeholder="t('management.emailFilterPlaceholder')"
              />
            </label>
            <BaseButton
              data-testid="user-filter-submit"
              type="submit"
              :loading="loading"
            >
              {{ t('common.search') }}
            </BaseButton>
            <BaseButton
              data-testid="user-filter-reset"
              variant="outline"
              :disabled="
                !usernameFilterInput &&
                !usernameFilter &&
                !emailFilterInput &&
                !emailFilter
              "
              @click="resetExactFilters"
            >
              {{ t('management.resetFilters') }}
            </BaseButton>
          </form>

          <BaseLoading v-if="loading && !users.length" />

          <div
            v-else-if="error"
            class="flex min-h-0 flex-1 items-center justify-center rounded-lg border border-line bg-surface-sunken py-16 text-center"
          >
            <p class="text-sm font-medium text-danger-700">{{ error }}</p>
          </div>

          <div
            v-else-if="!users.length"
            class="flex min-h-0 flex-1 items-center justify-center rounded-lg border border-line bg-surface-sunken py-16 text-center"
          >
            <p class="text-sm font-medium text-ink-500">
              {{ t('common.noData') }}
            </p>
          </div>

          <div
            v-else
            class="relative min-h-0 flex-1 overflow-auto rounded-lg border border-line bg-surface"
          >
            <table class="min-w-full divide-y divide-line">
              <thead class="sticky top-0 z-10 bg-surface-sunken">
                <tr>
                  <th class="table-head">ID</th>
                  <th class="table-head">{{ t('dashboard.username') }}</th>
                  <th class="table-head">{{ t('dashboard.email') }}</th>
                  <th class="table-head">{{ t('management.groups') }}</th>
                  <th class="table-head">{{ t('dashboard.isStaff') }}</th>
                  <th class="table-head">{{ t('management.isActive') }}</th>
                  <th class="table-head">{{ t('management.dateJoined') }}</th>
                  <th class="table-head">{{ t('common.actions') }}</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line bg-surface">
                <tr
                  v-for="user in users"
                  :key="user.id"
                  class="transition-colors hover:bg-line-soft"
                >
                  <td class="table-cell font-mono text-ink-500">
                    {{ user.id }}
                  </td>
                  <td class="table-cell">
                    <div class="font-medium text-ink-900">
                      {{ user.username }}
                    </div>
                    <div class="text-xs text-ink-400">
                      {{ user.display_name || '—' }}
                    </div>
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ user.email || '—' }}
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ joinNames(user.groups) }}
                  </td>
                  <td class="table-cell">
                    <span
                      v-if="user.is_staff"
                      class="inline-block rounded-md border border-primary-200 bg-primary-50 px-1.5 py-0.5 text-xs font-medium text-primary-700"
                    >
                      {{ t('common.yes') }}
                    </span>
                    <span v-else class="text-ink-400">—</span>
                  </td>
                  <td class="table-cell">
                    <StatusBadge
                      :status="
                        user.is_active !== false ? 'enabled' : 'disabled'
                      "
                    />
                  </td>
                  <td class="table-cell text-ink-500">
                    {{ formatDate(user.date_joined) }}
                  </td>
                  <td class="table-cell">
                    <div class="flex items-center gap-2">
                      <BaseButton
                        variant="outline"
                        size="sm"
                        @click="openEditModal(user)"
                      >
                        {{ t('common.edit') }}
                      </BaseButton>
                      <BaseButton
                        v-if="user.id !== currentUserId"
                        :variant="
                          user.is_active !== false ? 'danger' : 'primary'
                        "
                        size="sm"
                        :loading="togglingId === user.id"
                        @click="toggleActive(user)"
                      >
                        {{
                          user.is_active !== false
                            ? t('management.disable')
                            : t('management.enable')
                        }}
                      </BaseButton>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <PaginationBar
            v-if="!loading"
            class="flex-shrink-0"
            v-model:page-size="pageSize"
            :current-page="currentPage"
            :total="totalCount"
            @page-size-change="handlePageSizeChange"
            @prev="goPrevPage"
            @next="goNextPage"
          />
        </div>
      </section>

      <BaseDrawer
        :show="showModal"
        :title="modalTitle"
        :subtitle="form.username || ''"
        @close="closeModal"
      >
        <form id="user-form" class="space-y-4" @submit.prevent="submitUser">
          <p v-if="submitError" class="text-sm text-danger-700">
            {{ submitError }}
          </p>
          <div>
            <label class="mb-1 block text-sm font-medium text-ink-700">{{
              t('dashboard.username')
            }}</label>
            <input v-model="form.username" type="text" class="form-input" />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-ink-700">{{
              t('dashboard.email')
            }}</label>
            <input v-model="form.email" type="email" class="form-input" />
          </div>
          <div v-if="mode === 'create'">
            <label class="mb-1 block text-sm font-medium text-ink-700">{{
              t('password.reset.newPassword')
            }}</label>
            <input v-model="form.password" type="password" class="form-input" />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-ink-700">{{
              t('management.selectGroups')
            }}</label>
            <div
              class="max-h-40 space-y-1 overflow-y-auto rounded-lg border border-line bg-surface-sunken p-2"
            >
              <label
                v-for="group in groupOptions"
                :key="group.id"
                class="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm text-ink-700 hover:bg-surface"
              >
                <input
                  v-model="form.group_ids"
                  type="checkbox"
                  :value="group.id"
                  class="h-4 w-4 rounded border-line text-brand-600 focus:ring-brand-500"
                />
                {{ group.name }}
              </label>
              <p
                v-if="!groupOptions.length"
                class="px-2 py-1 text-xs text-ink-400"
              >
                {{ t('common.noData') }}
              </p>
            </div>
          </div>
          <div class="grid gap-4 md:grid-cols-2">
            <label
              class="flex cursor-pointer items-center gap-3 text-sm font-medium text-ink-700"
            >
              <input
                v-model="form.is_staff"
                type="checkbox"
                class="h-4 w-4 rounded border-line text-brand-600 focus:ring-brand-500"
              />
              {{ t('dashboard.isStaff') }}
            </label>
            <label
              class="flex cursor-pointer items-center gap-3 text-sm font-medium text-ink-700"
            >
              <input
                v-model="form.is_active"
                type="checkbox"
                class="h-4 w-4 rounded border-line text-brand-600 focus:ring-brand-500"
              />
              {{ t('management.isActive') }}
            </label>
          </div>
        </form>
        <template #footer>
          <div class="flex flex-row-reverse gap-2">
            <BaseButton
              variant="primary"
              :loading="submitLoading"
              type="submit"
              form="user-form"
            >
              {{ t('common.confirm') }}
            </BaseButton>
            <BaseButton variant="outline" @click="closeModal">
              {{ t('common.cancel') }}
            </BaseButton>
          </div>
        </template>
      </BaseDrawer>
    </div>
  </AdminLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import AdminLayout from '@/admin/layout/AdminLayout.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { useToast } from '@/composables/useToast'
import { useUserStore } from '@/store/user'
import { managementApi } from '@/admin/api'

const { t } = useI18n()
const { showSuccess, showError } = useToast()
const userStore = useUserStore()

const users = ref([])
const loading = ref(false)
const error = ref(null)
const togglingId = ref(null)
const currentPage = ref(1)
const pageSize = ref(20)
const totalCount = ref(0)
const usernameFilterInput = ref('')
const usernameFilter = ref('')
const emailFilterInput = ref('')
const emailFilter = ref('')

const currentUserId = computed(() => userStore.userInfo?.id)

const showModal = ref(false)
const mode = ref('create')
const editingUserId = ref(null)
const submitLoading = ref(false)
const submitError = ref(null)

const groupOptions = ref([])

const createEmptyForm = () => ({
  username: '',
  email: '',
  password: '',
  is_staff: false,
  is_active: true,
  group_ids: []
})

const form = ref(createEmptyForm())

const totalPages = computed(() =>
  totalCount.value > 0 ? Math.ceil(totalCount.value / pageSize.value) : 1
)

const modalTitle = computed(() =>
  mode.value === 'create'
    ? t('management.createUser')
    : t('management.editUser')
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
      : []
  }
  showModal.value = true
}

async function loadOptions() {
  try {
    const groupsData = await managementApi.getGroups({
      page: 1,
      page_size: 1000
    })
    groupOptions.value = Array.isArray(groupsData)
      ? groupsData
      : (groupsData?.results ?? [])
  } catch {
    groupOptions.value = []
  }
}

async function submitUser() {
  submitError.value = null
  const payload = {
    username: (form.value.username || '').trim(),
    email: (form.value.email || '').trim(),
    is_staff: !!form.value.is_staff,
    is_active: !!form.value.is_active,
    group_ids: Array.isArray(form.value.group_ids) ? form.value.group_ids : []
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

async function toggleActive(user) {
  if (togglingId.value) return
  togglingId.value = user.id
  const nextActive = user.is_active === false
  try {
    await managementApi.updateUser(user.id, { is_active: nextActive })
    showSuccess(t('management.statusUpdated'))
    await fetchUsers()
  } catch (e) {
    showError(e?.response?.data?.detail || e?.message || t('common.error'))
  } finally {
    togglingId.value = null
  }
}

function applyExactFilters() {
  usernameFilter.value = usernameFilterInput.value.trim()
  emailFilter.value = emailFilterInput.value.trim()
  currentPage.value = 1
  fetchUsers()
}

function resetExactFilters() {
  usernameFilterInput.value = ''
  usernameFilter.value = ''
  emailFilterInput.value = ''
  emailFilter.value = ''
  currentPage.value = 1
  fetchUsers()
}

async function fetchUsers() {
  loading.value = true
  error.value = null
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value
    }
    if (usernameFilter.value) {
      params.username = usernameFilter.value
    }
    if (emailFilter.value) {
      params.email = emailFilter.value
    }
    const data = await managementApi.getUsers(params)
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
  @apply border-b border-line px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-500;
}

.table-cell {
  @apply px-4 py-4 text-sm text-ink-700;
}

.form-input {
  @apply w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}
</style>
