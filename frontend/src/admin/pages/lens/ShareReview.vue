<template>
  <AdminLayout>
    <div class="w-full max-w-full p-6">
      <div class="mb-4">
        <h1 class="text-lg font-semibold text-gray-900">
          {{ t('lens.qa.adminTitle') }}
        </h1>
        <p class="mt-1 text-sm text-gray-500">
          {{ t('lens.qa.adminSubtitle') }}
        </p>
      </div>

      <div
        class="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm"
      >
        <div
          class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 px-6"
        >
          <div class="flex items-center gap-6">
            <button
              v-for="tab in tabs"
              :key="tab.key"
              type="button"
              class="qa-tab"
              :class="activeTab === tab.key ? 'qa-tab-active' : ''"
              @click="setTab(tab.key)"
            >
              {{ tab.label }}
            </button>
          </div>
          <BaseButton
            variant="outline"
            size="sm"
            :loading="loading"
            @click="load"
          >
            {{ t('common.refresh') }}
          </BaseButton>
        </div>

        <div class="p-6">
          <BaseLoading v-if="loading && !rows.length" />

          <div
            v-else-if="!rows.length"
            class="rounded-lg border border-gray-200 bg-gray-50 py-16 text-center"
          >
            <p class="text-sm font-medium text-gray-600">
              {{ t('common.noData') }}
            </p>
          </div>

          <div
            v-else
            class="relative overflow-x-auto rounded-lg border border-gray-200 bg-white"
          >
            <table class="min-w-full divide-y divide-gray-200">
              <thead class="bg-gradient-to-r from-gray-50 to-gray-100">
                <tr>
                  <th class="table-head">
                    {{ t('lens.qa.shareTitleLabel') }}
                  </th>
                  <th class="table-head">{{ t('lens.qa.assistant') }}</th>
                  <th class="table-head">{{ t('lens.qa.publishedBy') }}</th>
                  <th class="table-head">{{ t('lens.qa.publishedAt') }}</th>
                  <th class="table-head">{{ t('lens.qa.views') }}</th>
                  <th class="table-head text-right">
                    {{ t('common.actions') }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-gray-200 bg-white">
                <tr
                  v-for="row in pagedRows"
                  :key="row.uuid"
                  class="transition-colors hover:bg-gray-50"
                >
                  <td class="table-cell">
                    <div
                      class="max-w-[320px] truncate font-medium text-gray-800"
                      :title="row.title"
                    >
                      {{ row.title }}
                    </div>
                    <div
                      class="max-w-[320px] truncate text-xs text-gray-400"
                      :title="row.answer_snippet"
                    >
                      {{ row.answer_snippet }}
                    </div>
                  </td>
                  <td class="table-cell text-gray-600">
                    {{ row.assistant_name }}
                  </td>
                  <td class="table-cell text-gray-600">
                    {{ row.published_by }}
                  </td>
                  <td class="table-cell whitespace-nowrap text-gray-500">
                    {{ formatDate(row.published_at, 'yyyy-MM-dd HH:mm') }}
                  </td>
                  <td class="table-cell text-gray-500">{{ row.view_count }}</td>
                  <td class="table-cell">
                    <div class="flex items-center justify-end gap-2">
                      <a
                        :href="qaShareUrl(row.token)"
                        target="_blank"
                        rel="noopener"
                        class="text-xs text-gray-500 no-underline hover:text-primary-600"
                      >
                        {{ t('lens.qa.preview') }}
                      </a>
                      <BaseButton
                        v-if="!row.is_listed && row.status === 'published'"
                        variant="primary"
                        size="sm"
                        @click="apply(row, { is_listed: true })"
                      >
                        {{ t('lens.qa.approve') }}
                      </BaseButton>
                      <BaseButton
                        v-if="row.is_listed && row.status === 'published'"
                        variant="outline"
                        size="sm"
                        @click="apply(row, { is_listed: false })"
                      >
                        {{ t('lens.qa.unlist') }}
                      </BaseButton>
                      <BaseButton
                        v-if="row.status === 'published'"
                        variant="danger"
                        size="sm"
                        @click="apply(row, { status: 'hidden' })"
                      >
                        {{ t('lens.qa.hide') }}
                      </BaseButton>
                      <BaseButton
                        v-if="row.status === 'hidden'"
                        variant="outline"
                        size="sm"
                        @click="apply(row, { status: 'published' })"
                      >
                        {{ t('lens.qa.restore') }}
                      </BaseButton>
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
            :total="rows.length"
            @page-size-change="handlePageSizeChange"
            @prev="goPrevPage"
            @next="goNextPage"
          />
        </div>
      </div>
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
import { listAdminShares, updateAdminShare } from '@/api/lens'
import { formatDate } from '@/utils/formatting'
import { qaShareUrl } from '@/utils/lens'
import { useToast } from '@/composables/useToast'

const { t } = useI18n()
const { showSuccess, showError } = useToast()

const rows = ref([])
const loading = ref(true)
const activeTab = ref('pending')
const currentPage = ref(1)
const pageSize = ref(20)

const tabs = computed(() => [
  { key: 'pending', label: t('lens.qa.tabPending') },
  { key: 'listed', label: t('lens.qa.tabListed') },
  { key: 'hidden', label: t('lens.qa.tabHidden') }
])

const totalPages = computed(() =>
  Math.max(1, Math.ceil(rows.value.length / pageSize.value))
)
const pagedRows = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return rows.value.slice(start, start + pageSize.value)
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

const TAB_PARAMS = {
  pending: { listed: 'false', status: 'published' },
  listed: { listed: 'true', status: 'published' },
  hidden: { status: 'hidden' }
}

function extractRows(data) {
  if (Array.isArray(data)) {
    return data
  }
  return data?.results || []
}

async function load() {
  loading.value = true
  try {
    const data = await listAdminShares(TAB_PARAMS[activeTab.value])
    rows.value = extractRows(data)
  } catch {
    rows.value = []
  } finally {
    loading.value = false
  }
}

function setTab(key) {
  activeTab.value = key
  currentPage.value = 1
  load()
}

async function apply(row, payload) {
  try {
    await updateAdminShare(row.uuid, payload)
    showSuccess(t('lens.qa.actionDone'))
    load()
  } catch {
    showError(t('lens.qa.shareFailed'))
  }
}

onMounted(load)
</script>

<style scoped>
.table-head {
  @apply border-b border-gray-200 px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-gray-700;
}

.table-cell {
  @apply px-4 py-4 text-sm;
}

.qa-tab {
  @apply border-b-2 border-transparent py-3 text-sm font-medium text-gray-500 transition-colors;
}

.qa-tab:hover {
  @apply text-gray-700;
}

.qa-tab-active {
  @apply border-primary-500 text-primary-600;
}
</style>
