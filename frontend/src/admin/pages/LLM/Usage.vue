<template>
  <AdminLayout>
    <div
      class="flex h-auto min-h-0 w-full max-w-full flex-col p-0 md:h-full md:p-6"
    >
      <div class="mb-4 flex-shrink-0">
        <h1 class="text-lg font-semibold text-gray-900">
          {{ t('llm.usage.title') }}
        </h1>
        <p class="mt-1 text-sm text-gray-500">
          {{ t('llm.usage.subtitle') }}
        </p>
      </div>

      <div
        class="flex min-h-0 flex-col overflow-visible rounded-lg border-0 border-gray-200 bg-transparent shadow-none md:overflow-hidden md:border md:bg-white md:shadow-sm"
      >
        <div class="flex min-h-0 flex-col p-0 md:p-6">
          <div
            class="mb-4 flex flex-shrink-0 flex-col items-stretch gap-3 rounded-lg border border-gray-200 bg-white p-3 md:mb-6 md:flex-row md:flex-wrap md:items-center md:justify-between md:border-0 md:p-0"
          >
            <div
              class="flex w-full flex-col items-stretch gap-3 md:w-auto md:flex-1 md:flex-row md:flex-wrap md:items-center"
            >
              <span class="text-sm text-gray-600 whitespace-nowrap">{{
                t('llm.usage.filterByUser')
              }}</span>
              <BaseSelect
                v-model="selectedUserId"
                class="md:w-56"
                mobile-touch
                @change="onFiltersChanged"
              >
                <option value="">{{ t('llm.usage.allUsers') }}</option>
                <option v-for="u in userOptions" :key="u.id" :value="u.id">
                  {{ u.label }}
                </option>
              </BaseSelect>
              <input
                v-model="filters.model"
                type="text"
                :placeholder="t('llm.usage.filterModel')"
                class="min-h-11 w-full rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 md:min-h-0 md:w-44"
                @input="onModelInput"
              />
              <BaseSelect
                v-model="filters.success"
                class="md:w-28"
                mobile-touch
                @change="onFiltersChanged"
              >
                <option value="">{{ t('llm.usage.filterSuccess') }}</option>
                <option value="true">{{ t('common.yes') }}</option>
                <option value="false">{{ t('common.no') }}</option>
              </BaseSelect>
              <div
                class="flex w-full flex-col gap-2 md:w-auto md:flex-row md:items-center"
              >
                <span class="whitespace-nowrap text-sm text-gray-600">{{
                  t('llm.usage.dateRange')
                }}</span>
                <div
                  class="flex flex-col gap-2 md:flex-row md:items-center"
                  data-testid="usage-date-range"
                >
                  <BaseDateInput
                    v-model="filters.startDate"
                    compact
                    @change="onFiltersChanged"
                  />
                  <span class="hidden text-gray-400 md:inline">–</span>
                  <BaseDateInput
                    v-model="filters.endDate"
                    compact
                    @change="onFiltersChanged"
                  />
                </div>
              </div>
            </div>
            <BaseButton
              variant="outline"
              size="sm"
              :loading="loading"
              :title="t('common.refresh')"
              class="w-full shadow-sm transition-shadow hover:shadow-md md:w-auto"
              @click="fetchList"
            >
              <svg
                v-if="!loading"
                class="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                />
              </svg>
              <span class="sr-only">{{ t('common.refresh') }}</span>
            </BaseButton>
          </div>

          <BaseLoading v-if="loading && !items.length" />

          <div
            v-if="!loading && !items.length"
            class="rounded-lg border border-gray-200 bg-gray-50 py-16 text-center"
          >
            <p class="text-sm font-medium text-gray-600">
              {{ t('common.noData') }}
            </p>
          </div>

          <div
            v-if="!loading && items.length > 0"
            class="flex flex-col md:min-h-0"
          >
            <div
              data-testid="mobile-llm-usage-list"
              class="space-y-3 md:hidden"
            >
              <button
                v-for="u in items"
                :key="`mobile-${u.id}`"
                type="button"
                class="block w-full rounded-lg border border-gray-200 bg-white p-4 text-left shadow-sm transition-colors hover:border-primary-200 hover:bg-primary-50/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/30"
                :aria-label="`${t('common.viewDetails')}: ${u.model || '–'}`"
                @click="openDetail(u)"
              >
                <div class="flex items-start justify-between gap-3">
                  <div class="min-w-0 flex-1">
                    <h2 class="break-words text-sm font-semibold text-gray-900">
                      {{ u.model || '–' }}
                    </h2>
                    <p class="mt-1 text-xs text-gray-500">
                      {{ formatDate(u.created_at) }}
                      <span aria-hidden="true"> · </span>
                      {{ u.username || u.user_id || '-' }}
                    </p>
                  </div>
                  <span
                    class="inline-flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium"
                    :class="
                      u.success
                        ? 'bg-green-50 text-green-700'
                        : 'bg-red-50 text-red-700'
                    "
                  >
                    <span
                      class="h-1.5 w-1.5 rounded-full"
                      :class="u.success ? 'bg-green-500' : 'bg-red-500'"
                    />
                    {{ u.success ? t('common.yes') : t('common.no') }}
                  </span>
                </div>

                <dl
                  class="mt-4 grid grid-cols-3 divide-x divide-gray-100 rounded-lg bg-gray-50 py-3 text-center"
                >
                  <div class="px-2">
                    <dt class="text-[11px] text-gray-500">
                      {{ t('llm.usage.promptTokens') }}
                    </dt>
                    <dd class="mt-1 text-sm font-semibold text-gray-900">
                      {{ formatNum(u.prompt_tokens) }}
                    </dd>
                  </div>
                  <div class="px-2">
                    <dt class="text-[11px] text-gray-500">
                      {{ t('llm.usage.completionTokens') }}
                    </dt>
                    <dd class="mt-1 text-sm font-semibold text-gray-900">
                      {{ formatNum(u.completion_tokens) }}
                    </dd>
                  </div>
                  <div class="px-2">
                    <dt class="text-[11px] text-gray-500">
                      {{ t('llm.usage.totalTokens') }}
                    </dt>
                    <dd class="mt-1 text-sm font-semibold text-gray-900">
                      {{ formatNum(u.total_tokens) }}
                    </dd>
                  </div>
                </dl>

                <dl class="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                  <div>
                    <dt class="text-xs text-gray-500">
                      {{ t('llm.usage.e2eLatency') }}
                    </dt>
                    <dd class="mt-0.5 font-medium text-gray-800">
                      {{ formatE2eLatency(u.e2e_latency_sec) }}
                    </dd>
                  </div>
                  <div>
                    <dt class="text-xs text-gray-500">
                      {{ t('llm.usage.ttftSec') }}
                    </dt>
                    <dd class="mt-0.5 font-medium text-gray-800">
                      {{ formatTtft(u.ttft_sec) }}
                    </dd>
                  </div>
                  <div>
                    <dt class="text-xs text-gray-500">
                      {{ t('llm.usage.outputTps') }}
                    </dt>
                    <dd class="mt-0.5 font-medium text-gray-800">
                      {{ formatOutputTps(u.output_tps) }}
                    </dd>
                  </div>
                  <div>
                    <dt class="text-xs text-gray-500">
                      {{ t('llm.usage.costUsd') }}
                    </dt>
                    <dd class="mt-0.5 font-medium text-amber-700">
                      {{ formatCost(u.cost, u.cost_currency) }}
                    </dd>
                  </div>
                </dl>

                <div
                  class="mt-4 flex min-h-11 items-center justify-between border-t border-gray-100 pt-2 text-sm font-medium text-primary-700"
                >
                  <span>{{ t('common.viewDetails') }}</span>
                  <svg
                    class="h-4 w-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                    aria-hidden="true"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M9 5l7 7-7 7"
                    />
                  </svg>
                </div>
              </button>
            </div>

            <div
              data-testid="desktop-llm-usage-table"
              class="relative hidden max-h-full overflow-auto rounded-lg border border-gray-200 bg-white shadow-sm md:block"
            >
              <table class="min-w-full divide-y divide-gray-200">
                <thead
                  class="sticky top-0 z-10 bg-gradient-to-r from-gray-50 to-gray-100"
                >
                  <tr>
                    <th
                      class="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200"
                    >
                      {{ t('llm.usage.time') }}
                    </th>
                    <th
                      class="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200"
                    >
                      {{ t('llm.usage.user') }}
                    </th>
                    <th
                      class="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200"
                    >
                      {{ t('llm.usage.model') }}
                    </th>
                    <th
                      class="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200"
                    >
                      {{ t('llm.usage.promptTokens') }}
                    </th>
                    <th
                      class="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200"
                    >
                      {{ t('llm.usage.completionTokens') }}
                    </th>
                    <th
                      class="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200"
                    >
                      {{ t('llm.usage.totalTokens') }}
                    </th>
                    <th
                      class="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200"
                    >
                      {{ t('llm.usage.e2eLatency') }}
                    </th>
                    <th
                      class="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200"
                    >
                      {{ t('llm.usage.ttftSec') }}
                    </th>
                    <th
                      class="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200"
                    >
                      {{ t('llm.usage.outputTps') }}
                    </th>
                    <th
                      class="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200"
                    >
                      {{ t('llm.usage.costUsd') }}
                    </th>
                    <th
                      class="px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider border-b border-gray-200"
                    >
                      {{ t('llm.usage.success') }}
                    </th>
                  </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-100">
                  <tr
                    v-for="u in items"
                    :key="u.id"
                    class="hover:bg-gray-50 transition-colors duration-150 cursor-pointer"
                    @click="openDetail(u)"
                  >
                    <td
                      class="px-4 py-4 whitespace-nowrap text-sm text-gray-500"
                    >
                      {{ formatDate(u.created_at) }}
                    </td>
                    <td
                      class="px-4 py-4 whitespace-nowrap text-sm text-gray-500"
                    >
                      {{ u.username || u.user_id || '-' }}
                    </td>
                    <td
                      class="px-4 py-4 whitespace-nowrap text-sm font-medium text-gray-900"
                    >
                      {{ u.model || '–' }}
                    </td>
                    <td
                      class="px-4 py-4 whitespace-nowrap text-sm text-gray-500"
                    >
                      {{ formatNum(u.prompt_tokens) }}
                    </td>
                    <td
                      class="px-4 py-4 whitespace-nowrap text-sm text-gray-500"
                    >
                      {{ formatNum(u.completion_tokens) }}
                    </td>
                    <td
                      class="px-4 py-4 whitespace-nowrap text-sm text-gray-500"
                    >
                      {{ formatNum(u.total_tokens) }}
                    </td>
                    <td
                      class="px-4 py-4 whitespace-nowrap text-sm text-gray-600"
                    >
                      {{ formatE2eLatency(u.e2e_latency_sec) }}
                    </td>
                    <td
                      class="px-4 py-4 whitespace-nowrap text-sm text-gray-600"
                    >
                      {{ formatTtft(u.ttft_sec) }}
                    </td>
                    <td
                      class="px-4 py-4 whitespace-nowrap text-sm text-gray-600"
                    >
                      {{ formatOutputTps(u.output_tps) }}
                    </td>
                    <td
                      class="px-4 py-4 whitespace-nowrap text-sm text-amber-600 font-medium"
                    >
                      {{ formatCost(u.cost, u.cost_currency) }}
                    </td>
                    <td class="px-4 py-4 whitespace-nowrap">
                      <span
                        :class="
                          u.success
                            ? 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800'
                            : 'inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800'
                        "
                      >
                        {{ u.success ? t('common.yes') : t('common.no') }}
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <PaginationBar
              v-model:page-size="pageSize"
              :current-page="page"
              :total="total"
              @page-size-change="handlePageSizeChange"
              @prev="goPrevPage"
              @next="goNextPage"
            />
          </div>
        </div>
      </div>

      <!-- Detail drawer (right slide-out, same style as Records detail panel) -->
      <Transition
        enter-active-class="transition-opacity duration-200"
        enter-from-class="opacity-0"
        enter-to-class="opacity-100"
        leave-active-class="transition-opacity duration-150"
        leave-from-class="opacity-100"
        leave-to-class="opacity-0"
      >
        <div
          v-if="detailVisible"
          class="fixed inset-0 bg-gray-900 bg-opacity-50 z-40"
          aria-hidden="true"
          @click="closeDetail"
        />
      </Transition>
      <Transition
        enter-active-class="transition-transform duration-300 ease-out"
        enter-from-class="translate-x-full"
        enter-to-class="translate-x-0"
        leave-active-class="transition-transform duration-250 ease-in"
        leave-from-class="translate-x-0"
        leave-to-class="translate-x-full"
      >
        <div
          v-if="detailVisible"
          class="fixed inset-y-0 right-0 w-full max-w-2xl bg-white shadow-xl z-50 flex flex-col"
          role="dialog"
          aria-modal="true"
          :aria-label="t('llm.usage.detailTitle')"
        >
          <div
            class="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-gray-50 to-gray-100 flex-shrink-0"
          >
            <h2 class="text-lg font-semibold text-gray-900">
              {{ t('llm.usage.detailTitle') }}
            </h2>
            <button
              type="button"
              class="p-1.5 rounded-md text-gray-400 hover:text-gray-600 hover:bg-gray-100 transition-colors"
              :aria-label="t('common.close')"
              @click="closeDetail"
            >
              <svg
                class="w-5 h-5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </button>
          </div>
          <div
            v-if="selectedDetail"
            class="flex-1 overflow-y-auto p-6 space-y-6"
          >
            <div>
              <h3 class="text-sm font-semibold text-gray-900 mb-4">
                {{ t('llm.usage.basicInfo') }}
              </h3>
              <dl class="grid grid-cols-1 gap-4">
                <div>
                  <dt
                    class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                  >
                    {{ t('llm.usage.time') }}
                  </dt>
                  <dd class="text-sm font-medium text-gray-900">
                    {{ formatDate(selectedDetail.created_at) }}
                  </dd>
                </div>
                <div>
                  <dt
                    class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                  >
                    {{ t('llm.usage.startedAt') }}
                  </dt>
                  <dd class="text-sm font-medium text-gray-900">
                    {{
                      selectedDetail.started_at
                        ? formatDate(selectedDetail.started_at)
                        : '–'
                    }}
                  </dd>
                </div>
                <div>
                  <dt
                    class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                  >
                    {{ t('llm.usage.user') }}
                  </dt>
                  <dd class="text-sm font-medium text-gray-900">
                    {{
                      selectedDetail.username || selectedDetail.user_id || '–'
                    }}
                  </dd>
                </div>
                <div>
                  <dt
                    class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                  >
                    {{ t('llm.usage.configModel') }}
                  </dt>
                  <dd class="text-sm font-medium text-gray-900">
                    {{ selectedDetail.model || '–' }}
                  </dd>
                </div>
                <div>
                  <dt
                    class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                  >
                    {{ t('llm.usage.responseModel') }}
                  </dt>
                  <dd class="text-sm font-medium text-gray-900">
                    {{
                      selectedDetail.metadata &&
                      selectedDetail.metadata.response_model
                        ? selectedDetail.metadata.response_model
                        : '–'
                    }}
                  </dd>
                </div>
                <div>
                  <dt
                    class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                  >
                    {{ t('llm.usage.promptTokens') }}
                  </dt>
                  <dd class="text-sm font-medium text-gray-900">
                    {{ formatNum(selectedDetail.prompt_tokens) }}
                  </dd>
                </div>
                <div>
                  <dt
                    class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                  >
                    {{ t('llm.usage.completionTokens') }}
                  </dt>
                  <dd class="text-sm font-medium text-gray-900">
                    {{ formatNum(selectedDetail.completion_tokens) }}
                  </dd>
                </div>
                <div>
                  <dt
                    class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                  >
                    {{ t('llm.usage.totalTokens') }}
                  </dt>
                  <dd class="text-sm font-medium text-gray-900">
                    {{ formatNum(selectedDetail.total_tokens) }}
                  </dd>
                </div>
                <div>
                  <dt
                    class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                  >
                    {{ t('llm.usage.e2eLatency') }}
                  </dt>
                  <dd class="text-sm font-medium text-gray-900">
                    {{ formatE2eLatency(selectedDetail.e2e_latency_sec) }}
                  </dd>
                </div>
                <div v-if="selectedDetail.ttft_sec != null">
                  <dt
                    class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                  >
                    {{ t('llm.usage.ttftSec') }}
                  </dt>
                  <dd class="text-sm font-medium text-gray-900">
                    {{ formatTtft(selectedDetail.ttft_sec) }}
                  </dd>
                </div>
                <div>
                  <dt
                    class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                  >
                    {{ t('llm.usage.outputTps') }}
                  </dt>
                  <dd class="text-sm font-medium text-gray-900">
                    {{ formatOutputTps(selectedDetail.output_tps) }}
                  </dd>
                </div>
                <div>
                  <dt
                    class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                  >
                    {{ t('llm.usage.costUsd') }}
                  </dt>
                  <dd class="text-sm font-medium text-gray-900">
                    {{
                      formatCost(
                        selectedDetail.cost,
                        selectedDetail.cost_currency
                      )
                    }}
                  </dd>
                </div>
                <div>
                  <dt
                    class="text-xs font-semibold text-gray-700 mb-2 uppercase tracking-wider"
                  >
                    {{ t('llm.usage.success') }}
                  </dt>
                  <dd class="text-sm font-medium text-gray-900">
                    {{
                      selectedDetail.success ? t('common.yes') : t('common.no')
                    }}
                  </dd>
                </div>
              </dl>
            </div>
            <div
              v-if="selectedDetail.error"
              class="border-t border-gray-200 pt-6"
            >
              <h3 class="text-sm font-semibold text-gray-900 mb-4">
                {{ t('llm.usage.error') }}
              </h3>
              <div
                class="rounded-lg border border-red-200 bg-red-50 p-4 shadow-sm"
              >
                <pre
                  class="text-xs font-mono text-red-800 whitespace-pre-wrap break-words"
                  >{{ selectedDetail.error }}</pre
                >
              </div>
            </div>
            <div
              v-if="
                selectedDetail.metadata &&
                Object.keys(selectedDetail.metadata).length
              "
              class="border-t border-gray-200 pt-6"
            >
              <h3 class="text-sm font-semibold text-gray-900 mb-4">
                {{ t('llm.usage.metadata') }}
              </h3>
              <div
                class="rounded-lg border border-gray-200 bg-gray-50 p-4 shadow-sm"
              >
                <pre
                  class="text-xs font-mono text-gray-800 whitespace-pre-wrap break-words"
                  >{{ JSON.stringify(selectedDetail.metadata, null, 2) }}</pre
                >
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </AdminLayout>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useDebounce } from '@/composables/useDebounce'
import { useToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/utils/api'
import {
  formatNumLocale,
  formatCostLocale,
  formatDateIsoLocale
} from '@/utils/formatting'
import { llmAdminApi } from '@/admin/api'
import AdminLayout from '@/admin/layout/AdminLayout.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDateInput from '@/components/ui/BaseDateInput.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import BaseSelect from '@/components/ui/BaseSelect.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'

const { t, locale } = useI18n()
const { showError } = useToast()

function formatNum(value) {
  return formatNumLocale(value, locale.value)
}

function formatCost(value, currency = 'USD') {
  return formatCostLocale(value, currency, locale.value)
}

function formatDate(iso) {
  return formatDateIsoLocale(iso, locale.value)
}

function formatE2eLatency(sec) {
  if (sec == null || typeof sec !== 'number') return '–'
  if (sec < 1) return `${(sec * 1000).toFixed(0)} ms`
  return `${sec.toFixed(2)} s`
}

function formatTtft(sec) {
  if (sec == null || typeof sec !== 'number') return '–'
  if (sec < 1) return `${(sec * 1000).toFixed(0)} ms`
  return `${sec.toFixed(2)} s`
}

function formatOutputTps(tps) {
  if (tps == null || typeof tps !== 'number') return '–'
  return `${tps.toFixed(2)} tok/s`
}

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const filters = reactive({ model: '', success: '', startDate: '', endDate: '' })
const userOptions = ref([])
const selectedUserId = ref('')
const detailVisible = ref(false)
const selectedDetail = ref(null)

function openDetail(record) {
  selectedDetail.value = record
  detailVisible.value = true
}

function closeDetail() {
  detailVisible.value = false
  selectedDetail.value = null
}

function toUserLabel(u) {
  const parts = []
  if (u.username) parts.push(u.username)
  if (u.email) parts.push(u.email)
  if (u.nickname) parts.push(u.nickname)
  if (parts.length === 0 && u.id) parts.push(String(u.id))
  return parts.join(' · ')
}

async function fetchUserOptions() {
  try {
    const data = await llmAdminApi.getUsers({ page_size: 200 })
    const list = Array.isArray(data)
      ? data
      : Array.isArray(data?.results)
        ? data.results
        : []
    userOptions.value = list.map((u) => ({ id: u.id, label: toUserLabel(u) }))
  } catch {
    userOptions.value = []
  }
}

function onFiltersChanged() {
  page.value = 1
  fetchList()
}

function applyModelFilter() {
  page.value = 1
  fetchList()
}

const { debouncedFn: onModelInput, cancel: cancelDebounce } = useDebounce(
  applyModelFilter,
  300
)

const totalPages = computed(() =>
  Math.max(1, Math.ceil(total.value / pageSize.value))
)

function goPrevPage() {
  if (page.value <= 1) return
  page.value -= 1
  fetchList()
}

function goNextPage() {
  if (page.value >= totalPages.value) return
  page.value += 1
  fetchList()
}

function handlePageSizeChange() {
  page.value = 1
  fetchList()
}

async function fetchList() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    if (selectedUserId.value) params.user_id = selectedUserId.value
    if (filters.model) params.model = filters.model
    if (filters.success) params.success = filters.success
    if (filters.startDate) params.start_date = filters.startDate
    if (filters.endDate) params.end_date = filters.endDate
    const data = await llmAdminApi.getLLMUsage(params)
    items.value = data?.results ?? []
    total.value = data?.total ?? 0
  } catch (err) {
    showError(extractErrorMessage(err, t('common.error')))
    items.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  const now = new Date()
  const end = new Date(now)
  const start = new Date(now)
  start.setDate(start.getDate() - 3)
  const pad = (n) => String(n).padStart(2, '0')
  filters.startDate = `${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}`
  filters.endDate = `${end.getFullYear()}-${pad(end.getMonth() + 1)}-${pad(end.getDate())}`
  fetchUserOptions()
  fetchList()
})

onUnmounted(() => {
  cancelDebounce()
})
</script>
