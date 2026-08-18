<template>
  <section data-testid="run-trajectory-workbench" class="space-y-4">
    <BaseLoading v-if="loading && events.length === 0" />

    <template v-else>
      <dl class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <div class="trajectory-stat">
          <dt>{{ t('lensRuns.trajectoryEvents') }}</dt>
          <dd>{{ summary.event_count || 0 }}</dd>
        </div>
        <div class="trajectory-stat">
          <dt>{{ t('lensRuns.trajectoryDuration') }}</dt>
          <dd>{{ durationText(summary.duration_ms) }}</dd>
        </div>
        <div class="trajectory-stat">
          <dt>{{ t('lensRuns.trajectoryModels') }}</dt>
          <dd>{{ summary.model_calls || 0 }}</dd>
        </div>
        <div class="trajectory-stat">
          <dt>{{ t('lensRuns.trajectoryTools') }}</dt>
          <dd>{{ summary.tool_calls || 0 }}</dd>
        </div>
        <div class="trajectory-stat">
          <dt>{{ t('lensRuns.totalTokens') }}</dt>
          <dd>{{ (summary.total_tokens || 0).toLocaleString() }}</dd>
        </div>
        <div class="trajectory-stat trajectory-stat-error">
          <dt>{{ t('lensRuns.trajectoryErrors') }}</dt>
          <dd>{{ summary.error_count || 0 }}</dd>
        </div>
      </dl>

      <div
        v-if="events.length > 1"
        data-testid="trajectory-time-overview"
        class="rounded-lg border border-gray-200 bg-gray-50 px-3 py-3"
      >
        <div class="overflow-hidden rounded-md bg-white ring-1 ring-gray-200">
          <div
            v-for="lane in timelineLanes"
            :key="lane.key"
            class="flex items-center gap-2 border-b border-gray-100 px-2 py-1 last:border-b-0"
          >
            <span class="w-12 shrink-0 text-[11px] font-medium text-gray-500">
              {{ laneLabel(lane.key) }}
            </span>
            <div class="relative h-3 flex-1">
              <button
                v-for="step in lane.steps"
                :key="`overview-${lane.key}-${step.event.event_id}`"
                type="button"
                class="absolute top-0 h-full rounded-sm"
                :class="[
                  categoryColor(eventCategory(step.event)),
                  step.subagent ? 'ring-1 ring-amber-400' : ''
                ]"
                :style="{
                  left: `${step.left}%`,
                  width: `${step.width}%`
                }"
                :title="`${step.event.sequence} · ${step.event.event_type}`"
                @click="selectedEvent = step.event"
              />
            </div>
          </div>
        </div>
        <div class="mt-1 flex justify-between text-[11px] text-gray-400">
          <span>{{ timeText(summary.first_timestamp) }}</span>
          <span>{{ timeText(summary.last_timestamp) }}</span>
        </div>
      </div>

      <div class="flex flex-col gap-2 lg:flex-row lg:items-center">
        <div class="relative min-w-0 flex-1">
          <Search
            :size="15"
            class="pointer-events-none absolute left-2.5 top-2.5 text-gray-400"
          />
          <input
            v-model="query"
            data-testid="trajectory-search"
            class="w-full rounded-md border border-gray-300 py-2 pl-8 pr-3 text-sm focus:border-primary-400 focus:outline-none focus:ring-1 focus:ring-primary-400"
            :placeholder="t('lensRuns.trajectorySearch')"
          />
        </div>
        <div class="flex gap-1 overflow-x-auto pb-1 lg:pb-0">
          <button
            v-for="item in categoryOptions"
            :key="item.value"
            type="button"
            class="trajectory-filter"
            :class="category === item.value ? 'trajectory-filter-active' : ''"
            @click="category = item.value"
          >
            {{ item.label }}
            <span class="text-[10px] opacity-70">{{ item.count }}</span>
          </button>
        </div>
      </div>

      <div
        v-if="filteredEvents.length"
        class="grid min-h-[28rem] overflow-hidden rounded-lg border border-gray-200 lg:grid-cols-[minmax(0,3fr)_minmax(18rem,2fr)]"
      >
        <ol
          data-testid="trajectory-ledger"
          class="max-h-[42rem] overflow-y-auto divide-y divide-gray-100 bg-white"
        >
          <li v-for="row in rows" :key="row.event.event_id">
            <div
              role="button"
              tabindex="0"
              class="group flex w-full items-start gap-2 px-3 py-2.5 text-left hover:bg-gray-50"
              :class="
                selectedEvent?.event_id === row.event.event_id
                  ? 'bg-primary-50/70'
                  : ''
              "
              :style="{ paddingLeft: `${12 + row.depth * 18}px` }"
              @click="selectedEvent = row.event"
              @keydown.enter="selectedEvent = row.event"
            >
              <span class="mt-0.5 flex h-5 w-5 shrink-0 items-center">
                <button
                  v-if="row.hasChildren"
                  type="button"
                  class="rounded text-gray-400 hover:bg-gray-200"
                  :aria-label="t('lensRuns.trajectoryToggle')"
                  @click.stop="toggleCall(row.event.call_id)"
                >
                  <ChevronRight
                    v-if="collapsed.has(row.event.call_id)"
                    :size="15"
                  />
                  <ChevronDown v-else :size="15" />
                </button>
                <span
                  v-else
                  class="mx-auto h-2 w-2 rounded-full"
                  :class="categoryColor(eventCategory(row.event))"
                />
              </span>
              <span class="min-w-0 flex-1">
                <span class="flex items-center justify-between gap-3">
                  <span class="truncate text-sm font-medium text-gray-800">
                    {{ eventTitle(row.event) }}
                  </span>
                  <time class="shrink-0 text-[11px] tabular-nums text-gray-400">
                    #{{ row.event.sequence }} ·
                    {{ timeText(row.event.timestamp) }}
                  </time>
                </span>
                <span
                  class="mt-0.5 flex flex-wrap gap-x-3 text-xs text-gray-500"
                >
                  <span>{{ row.event.event_type }}</span>
                  <span v-if="eventMetric(row.event)">
                    {{ eventMetric(row.event) }}
                  </span>
                  <span v-if="row.event.attempt > 1">
                    attempt {{ row.event.attempt }}
                  </span>
                </span>
              </span>
            </div>
          </li>
        </ol>

        <aside
          data-testid="trajectory-inspector"
          class="max-h-[42rem] overflow-y-auto border-t border-gray-200 bg-gray-50 p-4 lg:border-l lg:border-t-0"
        >
          <template v-if="selectedEvent">
            <div class="flex items-start justify-between gap-3">
              <div>
                <p
                  class="text-xs font-medium uppercase tracking-wide text-gray-400"
                >
                  {{ t('lensRuns.trajectoryInspector') }}
                </p>
                <h3 class="mt-1 break-all text-sm font-semibold text-gray-900">
                  {{ selectedEvent.event_type }}
                </h3>
              </div>
              <span :class="statusClass(selectedEvent)">
                {{ selectedEvent.event_type.split('.').pop() }}
              </span>
            </div>
            <dl class="mt-4 grid grid-cols-2 gap-3 text-xs">
              <div>
                <dt class="text-gray-400">Sequence</dt>
                <dd class="mt-0.5 font-mono text-gray-700">
                  {{ selectedEvent.sequence }}
                </dd>
              </div>
              <div>
                <dt class="text-gray-400">Attempt</dt>
                <dd class="mt-0.5 font-mono text-gray-700">
                  {{ selectedEvent.attempt }}
                </dd>
              </div>
              <div class="col-span-2">
                <dt class="text-gray-400">Call / Parent</dt>
                <dd class="mt-0.5 break-all font-mono text-gray-700">
                  {{ selectedEvent.call_id || '-' }}<br />
                  {{ selectedEvent.parent_call_id || '-' }}
                </dd>
              </div>
              <div class="col-span-2">
                <dt class="text-gray-400">Timestamp</dt>
                <dd class="mt-0.5 break-all font-mono text-gray-700">
                  {{ selectedEvent.timestamp }}
                </dd>
              </div>
            </dl>
            <h4 class="mt-5 text-xs font-semibold text-gray-600">Payload</h4>
            <pre class="trajectory-json">{{
              pretty(selectedEvent.payload)
            }}</pre>
            <details class="mt-4">
              <summary class="cursor-pointer text-xs font-medium text-gray-500">
                {{ t('lensRuns.trajectoryRawEvent') }}
              </summary>
              <pre class="trajectory-json">{{ pretty(selectedEvent) }}</pre>
            </details>
          </template>
          <p v-else class="py-16 text-center text-sm text-gray-400">
            {{ t('lensRuns.trajectorySelectEvent') }}
          </p>
        </aside>
      </div>

      <p
        v-else
        class="rounded-lg border border-dashed border-gray-200 py-12 text-center text-sm text-gray-400"
      >
        {{ t('lensRuns.noTimeline') }}
      </p>

      <div v-if="hasMore" class="text-center">
        <BaseButton
          variant="outline"
          size="sm"
          :loading="loading"
          @click="loadMore"
        >
          {{ t('lensRuns.trajectoryLoadMore') }}
        </BaseButton>
      </div>
    </template>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ChevronDown, ChevronRight, Search } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { getAdminRunTrajectory } from '@/api/lens'
import { useToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/utils/api'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import {
  buildTimelineLanes,
  buildTrajectoryRows,
  eventCategory
} from './runTrajectory'

const props = defineProps({
  runUuid: { type: String, default: '' },
  active: { type: Boolean, default: false }
})

const { t } = useI18n()
const { showError } = useToast()
const events = ref([])
const summary = ref({})
const loading = ref(false)
const hasMore = ref(false)
const query = ref('')
const category = ref('all')
const selectedEvent = ref(null)
const collapsed = ref(new Set())
let filterTimer = null
let requestId = 0

const categoryOptions = computed(() => {
  const counts = summary.value.categories || {}
  const hiddenCategories = new Set(['checkpoint', 'system', 'user', 'run'])
  return [
    {
      value: 'all',
      label: t('lensRuns.trajectoryAll'),
      count: summary.value.event_count || 0
    },
    ...Object.entries(counts)
      .filter(([value]) => !hiddenCategories.has(value))
      .map(([value, count]) => ({
        value,
        label: value,
        count
      }))
  ]
})

const filteredEvents = computed(() => events.value)

const rows = computed(() =>
  buildTrajectoryRows(filteredEvents.value, collapsed.value)
)

const timelineLanes = computed(() =>
  buildTimelineLanes(events.value, summary.value)
)

function laneLabel(key) {
  return (
    {
      input: t('lensRuns.trajectoryLaneInput'),
      model: t('lensRuns.trajectoryLaneModel'),
      tools: t('lensRuns.trajectoryLaneTools')
    }[key] || key
  )
}

async function fetchTrajectory(append = false) {
  if (!props.runUuid) return
  const currentRequestId = ++requestId
  loading.value = true
  try {
    const afterSequence = append ? events.value.at(-1)?.sequence || 0 : 0
    const data = await getAdminRunTrajectory(props.runUuid, {
      page_size: 500,
      after_sequence: afterSequence,
      q: query.value.trim() || undefined,
      category: category.value === 'all' ? undefined : category.value
    })
    if (currentRequestId !== requestId) return
    events.value = append
      ? [...events.value, ...(data.results || [])]
      : data.results || []
    summary.value = data.summary || {}
    hasMore.value = Boolean(data.has_more)
    if (!append) selectedEvent.value = events.value[0] || null
  } catch (error) {
    if (currentRequestId !== requestId) return
    showError(extractErrorMessage(error, t('common.error')))
    hasMore.value = false
  } finally {
    if (currentRequestId === requestId) loading.value = false
  }
}

function reset() {
  requestId += 1
  events.value = []
  summary.value = {}
  selectedEvent.value = null
  collapsed.value = new Set()
  query.value = ''
  category.value = 'all'
  hasMore.value = false
}

function loadMore() {
  fetchTrajectory(true)
}

function toggleCall(callId) {
  const next = new Set(collapsed.value)
  if (next.has(callId)) next.delete(callId)
  else next.add(callId)
  collapsed.value = next
}

function eventTitle(event) {
  return event.payload?.name || event.payload?.model_ref || event.event_type
}

function eventMetric(event) {
  const payload = event.payload || {}
  const parts = []
  if (payload.duration_ms != null) parts.push(durationText(payload.duration_ms))
  if (payload.ttft_ms != null)
    parts.push(`TTFT ${durationText(payload.ttft_ms)}`)
  if (payload.usage?.total_tokens != null) {
    parts.push(`${payload.usage.total_tokens} tokens`)
  }
  return parts.join(' · ')
}

function categoryColor(value) {
  return (
    {
      model: 'bg-indigo-500',
      tool: 'bg-blue-500',
      subtool: 'bg-cyan-500',
      request: 'bg-emerald-500',
      checkpoint: 'bg-amber-500',
      retry: 'bg-orange-500',
      compaction: 'bg-purple-500',
      cancelled: 'bg-gray-500'
    }[value] || 'bg-gray-400'
  )
}

function statusClass(event) {
  const status = event.event_type.split('.').pop()
  const base = 'rounded px-2 py-0.5 text-[10px] font-semibold'
  if (['failed', 'cancelled', 'interrupted'].includes(status)) {
    return `${base} bg-red-100 text-red-700`
  }
  if (['completed', 'done'].includes(status)) {
    return `${base} bg-green-100 text-green-700`
  }
  return `${base} bg-gray-200 text-gray-600`
}

function durationText(value) {
  if (value === null || value === undefined) return '-'
  if (value < 1000) return `${value}ms`
  return `${(value / 1000).toFixed(1)}s`
}

function timeText(value) {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleTimeString([], { hour12: false })
}

function pretty(value) {
  return JSON.stringify(value, null, 2)
}

watch(
  () => props.runUuid,
  () => {
    reset()
    if (props.active) fetchTrajectory()
  }
)

watch([query, category], () => {
  if (!props.active) return
  clearTimeout(filterTimer)
  filterTimer = setTimeout(() => {
    fetchTrajectory()
  }, 250)
})

watch(
  () => props.active,
  (active) => {
    if (active && events.value.length === 0) fetchTrajectory()
  },
  { immediate: true }
)

onBeforeUnmount(() => clearTimeout(filterTimer))
</script>

<style scoped>
.trajectory-stat {
  @apply rounded-lg border border-gray-200 bg-white px-3 py-2.5;
}
.trajectory-stat dt {
  @apply truncate text-[11px] text-gray-500;
}
.trajectory-stat dd {
  @apply mt-1 text-lg font-semibold tabular-nums text-gray-900;
}
.trajectory-stat-error dd {
  @apply text-red-700;
}
.trajectory-filter {
  @apply inline-flex shrink-0 items-center gap-1 rounded-full border border-gray-200 bg-white px-2.5 py-1.5 text-xs font-medium text-gray-500 hover:bg-gray-50;
}
.trajectory-filter-active {
  @apply border-primary-200 bg-primary-50 text-primary-700;
}
.trajectory-json {
  @apply mt-2 max-h-96 overflow-auto whitespace-pre-wrap break-words rounded-md border border-gray-200 bg-white p-3 text-[11px] leading-5 text-gray-700;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
</style>
