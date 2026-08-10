<template>
  <BaseDrawer
    :show="show"
    :title="t('management.details.groupTitle')"
    :subtitle="group?.name || ''"
    width="2xl"
    @close="$emit('close')"
  >
    <template #actions>
      <BaseButton
        v-if="group"
        variant="outline"
        size="sm"
        @click="$emit('edit', group)"
      >
        {{ t('common.edit') }}
      </BaseButton>
    </template>
    <template #tabs>
      <div class="border-b border-line bg-surface">
        <div class="flex gap-5 px-6">
          <button
            v-for="tab in tabs"
            :key="tab.key"
            type="button"
            class="detail-tab"
            :class="activeTab === tab.key ? 'detail-tab-active' : ''"
            @click="activeTab = tab.key"
          >
            {{ tab.label }}
          </button>
        </div>
      </div>
    </template>

    <BaseLoading v-if="loading" />
    <div
      v-else-if="error"
      class="rounded-lg border border-danger-200 bg-danger-50 p-5 text-center"
    >
      <p class="text-sm text-danger-700">{{ error }}</p>
      <BaseButton
        class="mt-3"
        variant="outline"
        size="sm"
        @click="loadDetail"
        >{{ t('common.retry') }}</BaseButton
      >
    </div>
    <div
      v-else-if="detail"
      class="space-y-6"
      data-testid="group-detail-content"
    >
      <section class="pb-5">
        <div class="flex items-center gap-4">
          <div
            class="flex h-12 w-12 items-center justify-center rounded-full bg-brand-100 text-lg font-semibold text-brand-700"
          >
            {{ initials(detail.subject.name) }}
          </div>
          <div>
            <h3 class="text-lg font-semibold text-ink-900">
              {{ detail.subject.name }}
            </h3>
            <p class="text-sm text-ink-500">
              {{ t('management.details.groupSummary') }}
            </p>
          </div>
        </div>
      </section>
      <div class="grid grid-cols-3 border-y border-line divide-x divide-line">
        <StatCard
          :label="t('management.details.members')"
          :value="detail.stats.members"
        />
        <StatCard
          :label="t('management.details.assignedAssistants')"
          :value="detail.stats.assigned_assistants"
        />
        <StatCard
          :label="t('management.details.rolesPermissions')"
          :value="`${detail.stats.roles} / ${detail.stats.permissions}`"
        />
      </div>

      <section
        v-if="activeTab === 'overview'"
        class="border-b border-line pb-6"
      >
        <h3 class="font-semibold text-ink-900">
          {{ t('management.details.groupOverview') }}
        </h3>
        <dl class="mt-4 grid gap-4 text-sm sm:grid-cols-2">
          <div>
            <dt class="text-ink-400">{{ t('management.groupName') }}</dt>
            <dd class="mt-1 text-ink-800">{{ detail.subject.name }}</dd>
          </div>
          <div>
            <dt class="text-ink-400">{{ t('management.permissionCount') }}</dt>
            <dd class="mt-1 text-ink-800">
              {{ detail.subject.permission_count }}
            </dd>
          </div>
        </dl>
        <div class="mt-5">
          <p class="text-sm text-ink-400">{{ t('management.roles') }}</p>
          <div class="mt-2 flex flex-wrap gap-2">
            <span
              v-for="role in detail.subject.roles"
              :key="role.id"
              class="border-b border-line px-1 py-2 text-sm text-ink-700"
              >{{ role.name }}</span
            ><span
              v-if="!detail.subject.roles.length"
              class="text-sm text-ink-400"
              >{{ t('common.noData') }}</span
            >
          </div>
        </div>
      </section>

      <section
        v-else-if="activeTab === 'members'"
        class="overflow-x-auto border-b border-line"
      >
        <div
          class="flex flex-wrap items-end justify-between gap-3 border-b border-line px-5 py-4"
        >
          <h3 class="font-semibold text-ink-900">
            {{ t('management.details.members') }}
          </h3>
          <input
            v-model="searchInput"
            class="form-input max-w-xs"
            :placeholder="t('management.details.searchMembers')"
            @input="searchMembers"
          />
        </div>
        <BaseLoading v-if="membersLoading" />
        <div
          v-else-if="!detail.members.results.length"
          class="p-10 text-center text-sm text-ink-400"
        >
          {{ t('common.noData') }}
        </div>
        <table v-else class="min-w-full divide-y divide-line text-sm">
          <thead
            class="bg-surface-sunken text-left text-xs uppercase text-ink-400"
          >
            <tr>
              <th class="px-4 py-3">{{ t('dashboard.username') }}</th>
              <th class="px-4 py-3">{{ t('dashboard.email') }}</th>
              <th class="px-4 py-3">{{ t('management.isActive') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-line">
            <tr v-for="member in detail.members.results" :key="member.id">
              <td class="px-4 py-3 font-medium text-ink-800">
                {{ member.username }}
              </td>
              <td class="px-4 py-3 text-ink-500">{{ member.email || '—' }}</td>
              <td class="px-4 py-3">
                <StatusBadge
                  :status="member.is_active ? 'enabled' : 'disabled'"
                />
              </td>
            </tr>
          </tbody>
        </table>
        <PaginationBar
          v-model:page-size="memberPageSize"
          :current-page="memberPage"
          :total="detail.members.count"
          @page-size-change="changePageSize"
          @prev="previousPage"
          @next="nextPage"
        />
      </section>

      <section v-else class="overflow-x-auto border-b border-line">
        <h3 class="border-b border-line px-5 py-4 font-semibold text-ink-900">
          {{ t('management.details.assignedAssistants') }}
        </h3>
        <div
          v-if="!detail.assistants.length"
          class="p-10 text-center text-sm text-ink-400"
        >
          {{ t('common.noData') }}
        </div>
        <table v-else class="min-w-full divide-y divide-line text-sm">
          <thead
            class="bg-surface-sunken text-left text-xs uppercase text-ink-400"
          >
            <tr>
              <th class="px-4 py-3">{{ t('management.details.assistant') }}</th>
              <th class="px-4 py-3">
                {{ t('management.details.conversations') }}
              </th>
              <th class="px-4 py-3">{{ t('management.details.qaRecords') }}</th>
              <th class="px-4 py-3">{{ t('management.details.lastUsed') }}</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-line">
            <tr
              v-for="assistant in detail.assistants"
              :key="assistant.uuid"
              class="hover:bg-surface-sunken"
            >
              <td class="px-4 py-3">
                <button
                  class="font-medium text-brand-700 hover:underline"
                  @click="$emit('history', assistant)"
                >
                  {{ assistant.name }}
                </button>
                <div class="text-xs text-ink-400">{{ assistant.slug }}</div>
              </td>
              <td class="px-4 py-3 tabular-nums text-ink-600">
                {{ assistant.conversations }}
              </td>
              <td class="px-4 py-3 tabular-nums text-ink-600">
                {{ assistant.qa_records }}
              </td>
              <td class="px-4 py-3 text-ink-500">
                {{ formatDate(assistant.last_used_at) }}
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </div>
  </BaseDrawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { getAdminGroupAccessDetail } from '@/api/lens'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import StatCard from './DetailStatCard.vue'

const props = defineProps({
  show: Boolean,
  group: { type: Object, default: null }
})
defineEmits(['close', 'edit', 'history'])
const { t } = useI18n()
const detail = ref(null)
const loading = ref(false)
const membersLoading = ref(false)
const error = ref('')
const activeTab = ref('overview')
const searchInput = ref('')
const memberSearch = ref('')
const memberPage = ref(1)
const memberPageSize = ref(20)
const tabs = computed(() => [
  { key: 'overview', label: t('management.details.overview') },
  { key: 'members', label: t('management.details.members') },
  { key: 'assistants', label: t('management.details.assistants') }
])
function initials(value) {
  return (value || '?')
    .split(/\s+/)
    .map((word) => word[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}
function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '—'
}
async function loadDetail({ membersOnly = false } = {}) {
  if (!props.group?.id) return
  if (membersOnly) membersLoading.value = true
  else {
    loading.value = true
    error.value = ''
  }
  try {
    detail.value = await getAdminGroupAccessDetail(props.group.id, {
      page: memberPage.value,
      page_size: memberPageSize.value,
      search: memberSearch.value
    })
  } catch (e) {
    if (!membersOnly) {
      detail.value = null
      error.value = e?.response?.data?.detail || e?.message || t('common.error')
    }
  } finally {
    loading.value = false
    membersLoading.value = false
  }
}
const searchMembers = useDebounceFn(() => {
  memberSearch.value = searchInput.value.trim()
  memberPage.value = 1
  loadDetail({ membersOnly: true })
}, 300)
function changePageSize() {
  memberPage.value = 1
  loadDetail({ membersOnly: true })
}
function previousPage() {
  if (memberPage.value > 1) {
    memberPage.value -= 1
    loadDetail({ membersOnly: true })
  }
}
function nextPage() {
  const pages = Math.ceil(
    (detail.value?.members.count || 0) / memberPageSize.value
  )
  if (memberPage.value < pages) {
    memberPage.value += 1
    loadDetail({ membersOnly: true })
  }
}
watch(
  () => [props.show, props.group?.id],
  ([show]) => {
    if (show) {
      activeTab.value = 'overview'
      searchInput.value = ''
      memberSearch.value = ''
      memberPage.value = 1
      loadDetail()
    }
  }
)
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
