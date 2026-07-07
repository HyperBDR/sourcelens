<template>
  <AdminLayout>
    <div class="flex h-full min-h-0 w-full max-w-full flex-col p-6">
      <div class="mb-4 flex-shrink-0">
        <h1 class="text-lg font-semibold text-gray-900">
          {{ t('lensRuns.title') }}
        </h1>
        <p class="mt-1 text-sm text-gray-500">
          {{ t('lensRuns.subtitle') }}
        </p>
      </div>

      <div
        class="flex min-h-0 flex-col overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm"
      >
        <div class="flex min-h-0 flex-col p-6">
          <div
            class="mb-6 flex flex-shrink-0 flex-wrap items-center justify-between gap-3"
          >
            <div class="flex flex-wrap items-center gap-3">
              <input
                v-model="filters.q"
                type="text"
                :placeholder="t('lensRuns.filterKeyword')"
                class="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm w-52 focus:outline-none focus:ring-1 focus:ring-primary-500"
                @input="onFiltersChanged"
              />
              <input
                v-model="filters.username"
                type="text"
                :placeholder="t('lensRuns.filterUsername')"
                class="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm w-36 focus:outline-none focus:ring-1 focus:ring-primary-500"
                @input="onFiltersChanged"
              />
              <select
                v-model="filters.assistant"
                class="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm w-40 bg-white focus:outline-none focus:ring-1 focus:ring-primary-500"
                @change="onFiltersChanged"
              >
                <option value="">{{ t('lensRuns.assistantAll') }}</option>
                <option v-for="a in assistants" :key="a.slug" :value="a.slug">
                  {{ a.name }}
                </option>
              </select>
              <select
                v-model="filters.status"
                class="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm w-32 bg-white focus:outline-none focus:ring-1 focus:ring-primary-500"
                @change="onFiltersChanged"
              >
                <option value="">{{ t('lensRuns.statusAll') }}</option>
                <option value="done">{{ t('lensRuns.statusDone') }}</option>
                <option value="failed">{{ t('lensRuns.statusFailed') }}</option>
                <option value="streaming">
                  {{ t('lensRuns.statusRunning') }}
                </option>
                <option value="queued">{{ t('lensRuns.statusQueued') }}</option>
                <option value="cancelled">
                  {{ t('lensRuns.statusCancelled') }}
                </option>
              </select>
              <input
                v-model="filters.start_date"
                type="date"
                :lang="locale"
                :max="filters.end_date || undefined"
                class="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
                @change="onFiltersChanged"
              />
              <span class="text-gray-400">–</span>
              <input
                v-model="filters.end_date"
                type="date"
                :lang="locale"
                :min="filters.start_date || undefined"
                class="rounded-md border border-gray-300 px-2.5 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-primary-500"
                @change="onFiltersChanged"
              />
            </div>
            <div class="flex items-center gap-2">
              <BaseButton
                variant="outline"
                size="sm"
                :loading="loading"
                :title="t('common.refresh')"
                class="flex items-center gap-1"
                @click="fetchRuns"
              >
                {{ t('common.refresh') }}
              </BaseButton>
              <BaseButton variant="outline" size="sm" @click="resetFilters">
                {{ t('lensRuns.resetFilters') }}
              </BaseButton>
            </div>
          </div>

          <BaseLoading v-if="loading && runs.length === 0" />

          <div
            v-else-if="!loading && runs.length === 0"
            class="rounded-lg border border-gray-200 bg-gray-50 py-16 text-center"
          >
            <p class="text-sm font-medium text-gray-600">
              {{ t('lensRuns.noRuns') }}
            </p>
          </div>

          <div v-else class="flex min-h-0 flex-col">
            <div
              class="relative max-h-full overflow-auto rounded-lg border border-gray-200 bg-white shadow-sm"
            >
              <table class="min-w-full divide-y divide-gray-200">
                <thead class="sticky top-0 z-10 bg-gray-50">
                  <tr>
                    <th class="th">{{ t('lensRuns.colTime') }}</th>
                    <th class="th">{{ t('lensRuns.colUser') }}</th>
                    <th class="th">{{ t('lensRuns.colAssistant') }}</th>
                    <th class="th">{{ t('lensRuns.colQuestion') }}</th>
                    <th class="th">{{ t('lensRuns.colStatus') }}</th>
                    <th class="th">{{ t('lensRuns.colDuration') }}</th>
                    <th class="th">{{ t('lensRuns.colSteps') }}</th>
                  </tr>
                </thead>
                <tbody class="bg-white divide-y divide-gray-100">
                  <tr
                    v-for="r in runs"
                    :key="r.uuid"
                    class="hover:bg-gray-50 cursor-pointer transition-colors"
                    @click="openDetail(r.uuid)"
                  >
                    <td class="td text-gray-600 whitespace-nowrap">
                      {{ formatDate(r.created_at) }}
                    </td>
                    <td class="td text-gray-900 whitespace-nowrap">
                      {{ r.username || '-' }}
                    </td>
                    <td class="td text-gray-600 whitespace-nowrap">
                      {{ r.assistant_name || '-' }}
                    </td>
                    <td class="td text-gray-700 max-w-md truncate">
                      {{ r.question || '-' }}
                    </td>
                    <td class="td whitespace-nowrap">
                      <span :class="statusClass(r.status)">{{ r.status }}</span>
                    </td>
                    <td class="td text-gray-600 whitespace-nowrap tabular-nums">
                      {{ durationText(r.duration_seconds) }}
                    </td>
                    <td class="td text-gray-600 whitespace-nowrap tabular-nums">
                      {{ r.event_count }}
                      <span
                        v-if="r.subagent_count > 0"
                        class="ml-1 text-xs text-indigo-600"
                      >
                        · {{ t('lensRuns.subagents', { n: r.subagent_count }) }}
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

      <!-- Run detail right panel -->
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
          class="fixed inset-y-0 right-0 w-full max-w-3xl bg-white shadow-xl z-50 flex flex-col"
          role="dialog"
          aria-modal="true"
        >
          <div
            class="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-gray-50 to-gray-100 flex-shrink-0"
          >
            <h2 class="text-lg font-semibold text-gray-900">
              {{ t('lensRuns.detailTitle') }}
            </h2>
            <button
              class="text-gray-400 hover:text-gray-600"
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

          <div class="flex-1 overflow-y-auto">
            <BaseLoading v-if="detailLoading" class="m-6" />
            <div v-else-if="detail">
              <div
                class="sticky top-0 z-10 flex gap-5 border-b border-gray-200 bg-white px-6"
              >
                <button
                  class="detail-tab"
                  :class="
                    activeDetailTab === 'overview' ? 'detail-tab-active' : ''
                  "
                  @click="activeDetailTab = 'overview'"
                >
                  {{ t('lensRuns.tabOverview') }}
                </button>
                <button
                  class="detail-tab"
                  :class="
                    activeDetailTab === 'trace' ? 'detail-tab-active' : ''
                  "
                  @click="activeDetailTab = 'trace'"
                >
                  {{ t('lensRuns.tabTrace') }}
                  <span class="ml-1 text-xs text-gray-400">{{
                    detail.event_count
                  }}</span>
                </button>
              </div>

              <!-- Overview tab -->
              <div
                v-show="activeDetailTab === 'overview'"
                class="px-6 py-5 space-y-6"
              >
                <dl class="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
                  <div>
                    <dt class="text-gray-500">{{ t('lensRuns.colStatus') }}</dt>
                    <dd class="mt-0.5">
                      <span :class="statusClass(detail.status)">{{
                        detail.status
                      }}</span>
                    </dd>
                  </div>
                  <div>
                    <dt class="text-gray-500">{{ t('lensRuns.execTime') }}</dt>
                    <dd class="mt-0.5 text-gray-900 tabular-nums">
                      {{ durationText(detail.duration_seconds) }}
                    </dd>
                  </div>
                  <div>
                    <dt class="text-gray-500">{{ t('lensRuns.colUser') }}</dt>
                    <dd class="mt-0.5 text-gray-900">{{ detail.username }}</dd>
                  </div>
                  <div>
                    <dt class="text-gray-500">
                      {{ t('lensRuns.colAssistant') }}
                    </dt>
                    <dd class="mt-0.5 text-gray-900">
                      {{ detail.assistant_name }}
                      <span class="text-gray-400"
                        >· {{ detail.agent_rounds }}</span
                      >
                    </dd>
                  </div>
                  <div>
                    <dt class="text-gray-500">{{ t('lensRuns.lensnode') }}</dt>
                    <dd class="mt-0.5 text-gray-900">
                      {{ detail.lensnode_name || '-' }}
                    </dd>
                  </div>
                  <div>
                    <dt class="text-gray-500">{{ t('lensRuns.colSteps') }}</dt>
                    <dd class="mt-0.5 text-gray-900 tabular-nums">
                      {{ detail.event_count }}
                      <span
                        v-if="detail.subagent_count > 0"
                        class="text-indigo-600"
                      >
                        ·
                        {{
                          t('lensRuns.subagents', { n: detail.subagent_count })
                        }}
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt class="text-gray-500">{{ t('lensRuns.tokens') }}</dt>
                    <dd class="mt-0.5 text-gray-900 tabular-nums">
                      {{
                        detail.total_tokens
                          ? detail.total_tokens.toLocaleString()
                          : '-'
                      }}
                      <span v-if="detail.llm_calls" class="text-gray-400">
                        · {{ t('lensRuns.llmCalls', { n: detail.llm_calls }) }}
                      </span>
                      <span
                        v-if="detail.total_cost != null"
                        class="text-gray-400"
                      >
                        · ${{ detail.total_cost }}
                      </span>
                    </dd>
                  </div>
                  <div>
                    <dt class="text-gray-500">
                      {{ t('lensRuns.submittedAt') }}
                    </dt>
                    <dd class="mt-0.5 text-gray-900 tabular-nums">
                      {{ formatDateTime(detail.created_at) }}
                    </dd>
                  </div>
                  <div>
                    <dt class="text-gray-500">{{ t('lensRuns.queueTime') }}</dt>
                    <dd class="mt-0.5 text-gray-900 tabular-nums">
                      {{ queueText }}
                    </dd>
                  </div>
                  <div class="col-span-2">
                    <dt class="text-gray-500">
                      {{ t('lensRuns.execWindow') }}
                    </dt>
                    <dd class="mt-0.5 text-gray-900 tabular-nums">
                      {{ formatDateTime(detail.started_at) }}
                      <span class="text-gray-400">→</span>
                      {{ formatDateTime(detail.finished_at) }}
                    </dd>
                  </div>
                  <div v-if="detail.execution">
                    <dt class="text-gray-500">{{ t('lensRuns.task') }}</dt>
                    <dd class="mt-0.5 text-gray-900">
                      {{ detail.execution.task || '-' }}
                    </dd>
                  </div>
                  <div
                    v-if="
                      detail.execution &&
                      ((detail.execution.loaded_skills || []).length ||
                        (detail.execution.loaded_mcps || []).length)
                    "
                  >
                    <dt class="text-gray-500">{{ t('lensRuns.resources') }}</dt>
                    <dd class="mt-0.5 text-gray-900">
                      {{ (detail.execution.loaded_skills || []).length }} skills
                      · {{ (detail.execution.loaded_mcps || []).length }} mcps
                    </dd>
                  </div>
                  <div v-if="detail.execution" class="col-span-2">
                    <dt class="text-gray-500">
                      {{ t('lensRuns.targetDirs') }}
                    </dt>
                    <dd class="mt-0.5 text-xs text-gray-700 break-all">
                      {{
                        (detail.execution.target_dirs || [])
                          .map((d) => d.path || d)
                          .join(', ') || '-'
                      }}
                    </dd>
                  </div>
                </dl>

                <section>
                  <h3 class="text-sm font-semibold text-gray-700 mb-2">
                    {{ t('lensRuns.question') }}
                  </h3>
                  <div
                    class="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm text-gray-800 whitespace-pre-wrap"
                  >
                    {{ detail.question || '-' }}
                  </div>
                </section>

                <section v-if="detail.attachments && detail.attachments.length">
                  <h3 class="text-sm font-semibold text-gray-700 mb-2">
                    {{ t('lensRuns.attachments') }}
                  </h3>
                  <div class="flex flex-wrap gap-3">
                    <AuthImage
                      v-for="img in detail.attachments"
                      :key="img.uuid"
                      :src="img.url"
                      :alt="img.original_name || 'image'"
                      class="run-attachment"
                      zoomable
                    />
                  </div>
                  <p v-if="visionQuery" class="mt-2 text-xs text-gray-500">
                    {{ t('lensRuns.visionQuery') }}: {{ visionQuery }}
                  </p>
                </section>

                <section v-if="detail.answer">
                  <h3 class="text-sm font-semibold text-gray-700 mb-2">
                    {{ t('lensRuns.answer') }}
                  </h3>
                  <div class="rounded-md border border-gray-200 p-3">
                    <MarkdownRenderer :content="detail.answer" />
                  </div>
                </section>

                <section v-if="detail.error">
                  <h3 class="text-sm font-semibold text-red-600 mb-2">
                    {{ t('lensRuns.error') }}
                  </h3>
                  <pre
                    class="rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-700 whitespace-pre-wrap"
                    >{{ detail.error }}</pre
                  >
                </section>
              </div>

              <!-- Trace tab -->
              <div
                v-show="activeDetailTab === 'trace'"
                class="px-6 py-5 space-y-6"
              >
                <div
                  v-if="detail.llm_calls"
                  class="flex flex-wrap items-baseline gap-x-5 gap-y-1 rounded-md border border-indigo-100 bg-indigo-50 px-4 py-3 text-sm"
                >
                  <div>
                    <span class="text-gray-500">{{
                      t('lensRuns.totalTokens')
                    }}</span>
                    <span
                      class="ml-1.5 text-base font-semibold text-gray-900 tabular-nums"
                      >{{ (detail.total_tokens || 0).toLocaleString() }}</span
                    >
                  </div>
                  <div class="tabular-nums text-gray-600">
                    {{ (detail.prompt_tokens || 0).toLocaleString() }}↑
                    {{ (detail.completion_tokens || 0).toLocaleString() }}↓
                  </div>
                  <div class="text-gray-600">
                    {{ t('lensRuns.llmCalls', { n: detail.llm_calls }) }}
                  </div>
                  <div v-if="detail.total_cost != null" class="text-gray-600">
                    ${{ detail.total_cost }}
                  </div>
                </div>

                <ol v-if="timelineItems.length" class="timeline">
                  <li
                    v-for="(e, i) in timelineItems"
                    :key="i"
                    class="timeline-item"
                  >
                    <span class="timeline-dot" :class="e.dot" />
                    <div class="timeline-body">
                      <div class="timeline-row">
                        <span class="timeline-text">{{ e.text }}</span>
                        <span v-if="e.time" class="timeline-time">{{
                          e.time
                        }}</span>
                      </div>
                      <div v-if="e.detail" class="timeline-detail">
                        {{ e.detail }}
                      </div>
                      <div v-if="e.preview" class="timeline-preview">
                        {{ e.preview }}
                      </div>
                    </div>
                  </li>
                </ol>
                <p v-else class="text-sm text-gray-400">
                  {{ t('lensRuns.noTimeline') }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </div>
  </AdminLayout>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { format } from 'date-fns'
import { useDebounceFn } from '@vueuse/core'
import { useToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/utils/api'
import { getAdminRuns, getAdminRun, listAssistants } from '@/api/lens'
import AdminLayout from '@/admin/layout/AdminLayout.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import MarkdownRenderer from '@/components/ui/MarkdownRenderer.vue'
import AuthImage from '@/components/ui/AuthImage.vue'

const { t, locale } = useI18n()
const { showError } = useToast()

const loading = ref(false)
const runs = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const assistants = ref([])

const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref(null)
const selectedUuid = ref(null)
const activeDetailTab = ref('overview')

const filters = ref({
  q: '',
  username: '',
  assistant: '',
  status: '',
  start_date: '',
  end_date: ''
})

const totalPages = computed(() =>
  total.value > 0 ? Math.ceil(total.value / pageSize.value) : 1
)

const visionQuery = computed(() => {
  const step = (detail.value?.steps || []).find(
    (item) => item.step_type === 'multimodal'
  )
  return step?.multimodal?.query || ''
})

const TIMELINE_LABELS = {
  'llm.response': 'Model response',
  'deepagents.runtime.start': 'Runtime started',
  'deepagents.runtime.done': 'Runtime finished',
  'deepagents.runtime.error': 'Runtime error',
  'deepagents.agent.create': 'Agent created',
  'deepagents.agent.invoke': 'Calling model',
  'deepagents.agent.truncated': 'Reached turn limit',
  'deepagents.summarization.enabled': 'Context compaction on',
  'deepagents.summarization.compacted': 'Context compacted',
  'resources.materialized': 'Runtime resources loaded'
}

function timelineDot(e) {
  const a = e.activity || ''
  if ((e.agent_event || '').startsWith('llm.')) return 'dot-indigo'
  if (e.tool || a === 'running_tool') return 'dot-blue'
  if (a === 'thinking') return 'dot-purple'
  if (a === 'completed') return 'dot-green'
  if (a === 'loading_resources') return 'dot-amber'
  if ((e.agent_event || '').endsWith('.error')) return 'dot-red'
  return 'dot-gray'
}

function parseTimelineEvent(e) {
  let time = ''
  let body = e.message || ''
  const m = body.match(/^\[([\d-]+\s[\d:]+)\]\s*-\s*([\s\S]*)$/)
  if (m) {
    // lensnode stamps UTC; parse as UTC and format in the browser's
    // local timezone so it matches the rest of the page.
    const dt = new Date(m[1].replace(' ', 'T') + 'Z')
    time = isNaN(dt.getTime()) ? m[1].split(' ')[1] : format(dt, 'HH:mm:ss')
    body = m[2]
  }
  body = body.split('\n')[0].trim()
  let text
  if (e.tool) {
    const action = (e.agent_event || '').split('.').pop()
    text = action && action !== 'invoke' ? `${e.tool} (${action})` : e.tool
  } else if ((e.agent_event || '').startsWith('tool.')) {
    const segs = e.agent_event.split('.')
    const action = segs[segs.length - 1]
    const name = segs.slice(1, -1).join('.')
    text = action && action !== 'invoke' ? `${name} (${action})` : name
  } else if (e.agent_event && TIMELINE_LABELS[e.agent_event]) {
    text = TIMELINE_LABELS[e.agent_event]
  } else if (e.agent_event) {
    text = e.agent_event
  } else {
    text = body
  }
  const detailParts = []
  if (e.agent_event === 'llm.response') {
    if (e.summary) detailParts.push(e.summary)
    if (e.total_tokens != null) {
      detailParts.push(`${e.total_tokens} tokens`)
      if (e.prompt_tokens != null && e.completion_tokens != null) {
        detailParts.push(`${e.prompt_tokens}↑ ${e.completion_tokens}↓`)
      }
    }
    if (e.latency_ms != null) detailParts.push(msText(e.latency_ms))
  } else if (e.agent_event === 'deepagents.summarization.compacted') {
    if (e.before_tokens != null && e.after_tokens != null) {
      detailParts.push(`${kText(e.before_tokens)} → ${kText(e.after_tokens)}`)
    }
    if (e.saved_tokens != null)
      detailParts.push(`saved ${kText(e.saved_tokens)}`)
  } else if (e.agent_event === 'deepagents.summarization.enabled') {
    if (e.trigger_tokens != null) {
      detailParts.push(
        `trigger ${kText(e.trigger_tokens)} · keep ${kText(e.keep_tokens)}`
      )
    }
  } else if (e.summary) detailParts.push(e.summary)
  else if (e.path) detailParts.push(e.path)
  else if (e.query) detailParts.push(`"${e.query}"`)
  if (e.count > 1 && !e.summary) detailParts.push(`×${e.count}`)
  if (e.duration_ms != null) detailParts.push(msText(e.duration_ms))
  return {
    time,
    text,
    detail: detailParts.join('  ·  '),
    preview: e.preview || '',
    dot: timelineDot(e)
  }
}

const timelineItems = computed(() => {
  if (!detail.value?.steps) return []
  const out = []
  for (const step of detail.value.steps) {
    for (const e of step.events || []) out.push(parseTimelineEvent(e))
  }
  return out
})

function formatDate(val) {
  if (!val) return '-'
  try {
    return format(new Date(val), 'yyyy-MM-dd HH:mm')
  } catch {
    return String(val)
  }
}

function msText(ms) {
  if (ms === null || ms === undefined) return ''
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

function kText(tokens) {
  if (tokens === null || tokens === undefined) return ''
  if (tokens < 1000) return `${tokens}`
  return `${(tokens / 1000).toFixed(1)}K`
}

function durationText(sec) {
  if (sec === null || sec === undefined) return '-'
  if (sec < 60) return `${Math.round(sec)}s`
  return `${Math.floor(sec / 60)}m ${Math.round(sec % 60)}s`
}

function statusClass(status) {
  const s = (status || '').toLowerCase()
  const base = 'text-xs font-medium px-2 py-0.5 rounded'
  if (s === 'done') return `${base} bg-green-100 text-green-800`
  if (s === 'failed') return `${base} bg-red-100 text-red-800`
  if (s === 'cancelled') return `${base} bg-gray-100 text-gray-600`
  if (['running', 'streaming', 'queued'].includes(s))
    return `${base} bg-blue-100 text-blue-800`
  return `${base} bg-gray-100 text-gray-600`
}

function formatDateTime(val) {
  if (!val) return '-'
  try {
    return format(new Date(val), 'MM-dd HH:mm:ss')
  } catch {
    return String(val)
  }
}

const queueText = computed(() => {
  const d = detail.value
  if (!d?.created_at || !d?.started_at) return '-'
  const sec = (new Date(d.started_at) - new Date(d.created_at)) / 1000
  if (sec < 0) return '-'
  return sec < 1 ? '<1s' : durationText(sec)
})

function onFiltersChanged() {
  page.value = 1
  debouncedFetch()
}

const debouncedFetch = useDebounceFn(() => fetchRuns(), 300)

function resetFilters() {
  filters.value = {
    q: '',
    username: '',
    assistant: '',
    status: '',
    start_date: '',
    end_date: ''
  }
  page.value = 1
  fetchRuns()
}

function handlePageSizeChange() {
  page.value = 1
  fetchRuns()
}

function goPrevPage() {
  if (page.value <= 1) return
  page.value -= 1
  fetchRuns()
}

function goNextPage() {
  if (page.value >= totalPages.value) return
  page.value += 1
  fetchRuns()
}

function openDetail(uuid) {
  selectedUuid.value = uuid
  detailVisible.value = true
  detail.value = null
  activeDetailTab.value = 'overview'
}

function closeDetail() {
  detailVisible.value = false
  selectedUuid.value = null
  detail.value = null
}

async function fetchRuns() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize.value }
    for (const [k, v] of Object.entries(filters.value)) {
      if (v) params[k] = v
    }
    const data = await getAdminRuns(params)
    runs.value = data?.results ?? []
    total.value = data?.total ?? 0
  } catch (e) {
    showError(extractErrorMessage(e, t('common.error')))
    runs.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function fetchDetail() {
  if (!selectedUuid.value) return
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await getAdminRun(selectedUuid.value)
  } catch (e) {
    showError(extractErrorMessage(e, t('common.error')))
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

onMounted(async () => {
  try {
    assistants.value = await listAssistants()
  } catch {
    assistants.value = []
  }
  fetchRuns()
})

watch(detailVisible, (visible) => {
  if (visible && selectedUuid.value) fetchDetail()
})
</script>

<style scoped>
.run-attachment :deep(.auth-image) {
  max-width: 180px;
  max-height: 180px;
  object-fit: cover;
  border: 1px solid #e5e7eb;
}
.th {
  @apply px-4 py-3 text-left text-xs font-semibold text-gray-700 uppercase tracking-wider;
}
.td {
  @apply px-4 py-3 text-sm;
}

.detail-tab {
  @apply py-3 text-sm font-medium border-b-2 border-transparent text-gray-500 transition-colors;
}
.detail-tab:hover {
  @apply text-gray-700;
}
.detail-tab-active {
  @apply border-primary-500 text-primary-600;
}

.timeline {
  @apply pl-1;
}
.timeline-item {
  @apply relative pl-5 pb-4;
  border-left: 1.5px solid #e5e7eb;
}
.timeline-item:last-child {
  @apply pb-0;
  border-left-color: transparent;
}
.timeline-dot {
  @apply absolute left-0 top-1 h-2.5 w-2.5 rounded-full ring-2 ring-white;
  transform: translateX(-50%);
}
.timeline-row {
  @apply flex items-baseline justify-between gap-3;
}
.timeline-text {
  @apply text-sm text-gray-800 break-words;
}
.timeline-time {
  @apply shrink-0 text-xs text-gray-400 tabular-nums;
}
.timeline-detail {
  @apply mt-0.5 text-xs text-gray-500 break-all;
}

.timeline-preview {
  @apply mt-1 rounded border border-gray-100 bg-gray-50 px-2 py-1 text-xs
    text-gray-600 break-all;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.dot-blue {
  background: #3b82f6;
}
.dot-purple {
  background: #8b5cf6;
}
.dot-green {
  background: #10b981;
}
.dot-amber {
  background: #f59e0b;
}
.dot-red {
  background: #ef4444;
}
.dot-gray {
  background: #9ca3af;
}
.dot-indigo {
  background: #6366f1;
}
</style>
