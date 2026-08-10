<template>
  <BaseDrawer
    :show="show"
    :title="t('management.details.userTitle')"
    :subtitle="drawerSubtitle"
    width="2xl"
    @close="$emit('close')"
  >
    <template #actions>
      <BaseButton
        v-if="user"
        variant="outline"
        size="sm"
        @click="$emit('edit', user)"
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
      <BaseButton class="mt-3" variant="outline" size="sm" @click="loadDetail">
        {{ t('common.retry') }}
      </BaseButton>
    </div>
    <div
      v-else-if="detail"
      class="min-w-0 space-y-6 overflow-x-hidden"
      data-testid="user-detail-content"
    >
      <section class="flex flex-wrap items-center gap-4 pb-5">
        <div
          class="flex h-14 w-14 items-center justify-center rounded-full bg-brand-100 text-lg font-semibold text-brand-700"
        >
          {{ initials(detail.subject.username) }}
        </div>
        <div class="min-w-0 flex-1">
          <h3 class="select-text truncate text-lg font-semibold text-ink-900">
            {{ detail.subject.username }}
          </h3>
          <p
            class="select-text truncate text-sm text-ink-500"
            :title="detail.subject.email || ''"
          >
            {{ detail.subject.email || '—' }}
          </p>
          <div class="mt-2 flex flex-wrap gap-2 text-xs">
            <StatusBadge
              :status="detail.subject.is_active ? 'enabled' : 'disabled'"
            />
            <span
              class="rounded-md border border-line bg-surface px-2 py-1 text-ink-600"
            >
              {{
                detail.subject.is_staff
                  ? t('management.details.staffUser')
                  : t('management.details.regularUser')
              }}
            </span>
            <span
              v-for="group in detail.subject.groups"
              :key="group.id"
              class="rounded-md border border-line bg-surface px-2 py-1 text-ink-600"
            >
              {{ group.name }}
            </span>
          </div>
        </div>
      </section>

      <div
        class="grid grid-cols-2 divide-x divide-line border-y border-line sm:grid-cols-4"
      >
        <StatCard
          :label="t('management.details.assignedAssistants')"
          :value="detail.stats.assigned_assistants"
        />
        <StatCard
          :label="t('management.details.conversations')"
          :value="detail.stats.conversations"
        />
        <StatCard
          :label="t('management.details.qaRecords')"
          :value="detail.stats.qa_records"
        />
        <StatCard
          :label="t('management.details.lastActive')"
          :value="formatDate(detail.stats.last_active_at)"
          compact
        />
      </div>

      <section
        v-if="activeTab === 'overview'"
        class="border-b border-line pb-6"
      >
        <h3 class="font-semibold text-ink-900">
          {{ t('management.details.accountOverview') }}
        </h3>
        <dl class="mt-4 grid gap-4 text-sm sm:grid-cols-2">
          <div class="min-w-0">
            <dt class="text-ink-400">{{ t('dashboard.username') }}</dt>
            <dd
              class="select-text mt-1 truncate text-ink-800"
              :title="detail.subject.username"
            >
              {{ detail.subject.username }}
            </dd>
          </div>
          <div class="min-w-0">
            <dt class="text-ink-400">{{ t('dashboard.email') }}</dt>
            <dd
              class="select-text mt-1 truncate text-ink-800"
              :title="detail.subject.email || ''"
            >
              {{ detail.subject.email || '—' }}
            </dd>
          </div>
          <div class="min-w-0">
            <dt class="text-ink-400">{{ t('management.groups') }}</dt>
            <dd class="mt-1 truncate text-ink-800" :title="groupNames">
              {{ groupNames }}
            </dd>
          </div>
          <div class="min-w-0">
            <dt class="text-ink-400">
              {{ t('management.details.accountType') }}
            </dt>
            <dd class="mt-1 text-ink-800">
              {{
                detail.subject.is_staff
                  ? t('management.details.staffUser')
                  : t('management.details.regularUser')
              }}
            </dd>
          </div>
        </dl>
      </section>

      <section
        v-else-if="activeTab === 'assistants'"
        class="overflow-x-auto border-b border-line"
      >
        <div
          class="flex items-center justify-between border-b border-line px-5 py-4"
        >
          <h3 class="font-semibold text-ink-900">
            {{ t('management.details.relatedAssistants') }}
          </h3>
          <button
            class="text-sm font-medium text-brand-700 hover:underline"
            @click="$emit('history', null)"
          >
            {{ t('management.details.viewAllHistory') }}
          </button>
        </div>
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
              <th class="px-4 py-3">{{ t('management.details.access') }}</th>
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
              <td class="px-4 py-3 text-ink-600">
                {{ accessLabels(assistant.access_sources) }}
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

      <section v-else class="border-b border-line pb-6">
        <h3 class="font-semibold text-ink-900">{{ t('management.groups') }}</h3>
        <div class="mt-4 flex flex-wrap gap-2">
          <span
            v-for="group in detail.subject.groups"
            :key="group.id"
            class="border-b border-line px-1 py-2 text-sm text-ink-700"
            >{{ group.name }}</span
          >
          <span
            v-if="!detail.subject.groups.length"
            class="text-sm text-ink-400"
            >{{ t('common.noData') }}</span
          >
        </div>
      </section>
    </div>
  </BaseDrawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { getAdminUserAccessDetail } from '@/api/lens'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import StatCard from './DetailStatCard.vue'

const props = defineProps({
  show: Boolean,
  user: { type: Object, default: null }
})
defineEmits(['close', 'edit', 'history'])
const { t } = useI18n()
const detail = ref(null)
const loading = ref(false)
const error = ref('')
const activeTab = ref('overview')
const tabs = computed(() => [
  { key: 'overview', label: t('management.details.overview') },
  { key: 'assistants', label: t('management.details.assistantsActivity') },
  { key: 'groups', label: t('management.groups') }
])
const drawerSubtitle = computed(() => {
  const value = props.user?.username || ''
  if (value.length <= 72) {
    return value
  }
  return `${value.slice(0, 72)}...`
})
const groupNames = computed(
  () =>
    detail.value?.subject.groups.map((group) => group.name).join(', ') || '—'
)

function initials(value) {
  return (value || '?').slice(0, 2).toUpperCase()
}
function formatDate(value) {
  return value ? new Date(value).toLocaleString() : '—'
}
function accessLabels(sources) {
  return (sources || [])
    .map((source) => t(`management.details.accessSources.${source}`))
    .join(', ')
}
async function loadDetail() {
  if (!props.user?.id) return
  loading.value = true
  error.value = ''
  try {
    detail.value = await getAdminUserAccessDetail(props.user.id)
  } catch (e) {
    detail.value = null
    error.value = e?.response?.data?.detail || e?.message || t('common.error')
  } finally {
    loading.value = false
  }
}
watch(
  () => [props.show, props.user?.id],
  ([show]) => {
    if (show) {
      activeTab.value = 'overview'
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
