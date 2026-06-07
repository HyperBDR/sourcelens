<template>
  <AppLayout>
    <div class="mx-auto grid max-w-7xl gap-5 xl:grid-cols-[300px_1fr]">
      <aside class="space-y-4">
        <section class="rounded-lg border border-gray-200 bg-white">
          <div class="border-b border-gray-200 px-4 py-3">
            <h1 class="text-base font-semibold text-gray-900">Lens Chat</h1>
          </div>
          <div class="space-y-3 p-4">
            <select v-model="selectedAssistantUuid" class="input">
              <option
                v-for="assistant in assistants"
                :key="assistant.uuid"
                :value="assistant.uuid"
              >
                {{ assistant.name }}
              </option>
            </select>
            <BaseButton block variant="secondary" @click="createNewSession">
              新建会话
            </BaseButton>
          </div>
        </section>

        <section class="rounded-lg border border-gray-200 bg-white">
          <div class="border-b border-gray-200 px-4 py-3">
            <h2 class="text-sm font-semibold text-gray-900">Sessions</h2>
          </div>
          <div class="max-h-[520px] divide-y divide-gray-100 overflow-y-auto">
            <button
              v-for="session in sessions"
              :key="session.uuid"
              class="w-full px-4 py-3 text-left hover:bg-gray-50"
              :class="selectedSessionUuid === session.uuid ? 'bg-blue-50' : ''"
              @click="selectSession(session)"
            >
              <div class="truncate text-sm font-medium text-gray-900">
                {{ session.title || '未命名会话' }}
              </div>
              <div class="mt-1 text-xs text-gray-500">
                {{ formatDateTime(session.created_at) }}
              </div>
            </button>
          </div>
        </section>
      </aside>

      <main class="chat-shell">
        <header class="border-b border-gray-200 px-5 py-4">
          <div class="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 class="text-lg font-semibold text-gray-900">
                {{ selectedAssistant?.name || '等待选择助手' }}
              </h2>
              <p class="mt-1 text-sm text-gray-500">
                {{ selectedAssistant?.selected_task || '-' }} ·
                {{ selectedSessionUuid || 'no session' }}
              </p>
            </div>
            <StatusBadge :status="currentRun?.status || 'pending'" />
          </div>
        </header>

        <section class="flex-1 space-y-3 overflow-y-auto bg-gray-50 p-5">
          <article
            v-for="message in messages"
            :key="message.uuid"
            class="max-w-3xl rounded-lg border px-4 py-3"
            :class="
              message.role === 'user'
                ? 'ml-auto border-blue-200 bg-blue-50'
                : 'border-gray-200 bg-white'
            "
          >
            <div class="text-xs font-semibold uppercase text-gray-500">
              {{ message.role }}
            </div>
            <div
              class="mt-2 whitespace-pre-wrap text-sm leading-6 text-gray-800"
            >
              {{ message.content || '（空）' }}
            </div>
          </article>

          <article v-if="showLiveAnswer" class="stream-card">
            <div class="flex items-center justify-between gap-3">
              <div class="text-xs font-semibold uppercase text-gray-500">
                assistant
              </div>
              <div
                v-if="isRunActive"
                class="text-xs font-medium text-blue-600"
              >
                {{ liveStatusText }}
              </div>
            </div>
            <div
              v-if="partialAnswer || streamError"
              class="mt-2 whitespace-pre-wrap text-sm leading-6 text-gray-800"
            >
              {{ partialAnswer || streamError }}
              <span v-if="showCursor" class="stream-cursor" />
            </div>
            <div
              v-else
              class="mt-2 flex items-center gap-2 text-sm text-gray-500"
            >
              <span>{{ t('lens.chat.thinking') }}</span>
              <span class="typing-dots" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
            </div>
          </article>

          <section
            v-if="activityEvents.length"
            class="activity-card"
          >
            <div class="flex items-center justify-between gap-3">
              <div>
                <h3 class="text-sm font-semibold text-gray-900">
                  {{ t('lens.chat.agentActivity') }}
                </h3>
                <p class="mt-1 text-xs text-gray-500">
                  {{ currentActivityText }}
                </p>
              </div>
              <span
                v-if="isRunActive"
                class="h-2 w-2 rounded-full bg-blue-500"
              />
            </div>
            <ol class="mt-3 space-y-2">
              <li
                v-for="event in activityEvents"
                :key="event.id"
                class="activity-item"
              >
                <div class="min-w-0">
                  <div class="text-sm font-medium text-gray-900">
                    {{ activityTitle(event) }}
                  </div>
                  <div
                    v-if="activityDetail(event)"
                    class="mt-1 truncate text-xs text-gray-500"
                  >
                    {{ activityDetail(event) }}
                  </div>
                </div>
                <span class="shrink-0 text-xs text-gray-400">
                  {{ formatDateTime(event.ts) }}
                </span>
              </li>
            </ol>
          </section>

          <section
            v-if="streamEvents.length"
            class="max-w-4xl rounded-lg border border-gray-200 bg-white"
          >
            <button
              class="flex w-full items-center justify-between border-b border-gray-100 px-4 py-3 text-left"
              type="button"
              @click="timelineOpen = !timelineOpen"
            >
              <h3 class="text-sm font-semibold text-gray-900">
                {{ t('lens.chat.executionTimeline') }}
              </h3>
              <span class="text-xs text-gray-500">
                {{
                  timelineOpen
                    ? t('lens.chat.hideTimeline')
                    : t('lens.chat.showTimeline', {
                        count: streamEvents.length
                      })
                }}
              </span>
            </button>
            <ol v-if="timelineOpen" class="divide-y divide-gray-100">
              <li
                v-for="event in streamEvents"
                :key="event.id"
                class="px-4 py-3"
              >
                <div class="flex flex-wrap items-center gap-2">
                  <StatusBadge :status="event.status || 'processing'" />
                  <span class="text-xs text-gray-500">
                    {{ event.label }}
                  </span>
                  <span class="text-xs text-gray-400">
                    {{ formatDateTime(event.ts) }}
                  </span>
                </div>
                <pre
                  v-if="event.message"
                  class="timeline-message"
                >{{ event.message }}</pre>
              </li>
            </ol>
          </section>
        </section>

        <footer class="border-t border-gray-200 p-4">
          <div class="grid gap-3 lg:grid-cols-[1fr_auto]">
            <textarea
              v-model="question"
              class="input min-h-[96px] resize-none"
              :placeholder="t('lens.chat.questionPlaceholder')"
            />
            <div class="flex flex-col gap-2">
              <label class="flex items-center gap-2 text-sm text-gray-600">
                <input v-model="runInline" type="checkbox" />
                {{ t('lens.chat.runInline') }}
              </label>
              <BaseButton
                :disabled="!selectedSessionUuid || !question.trim()"
                :loading="loading.run"
                variant="primary"
                @click="submit"
              >
                {{ t('common.submit') }}
              </BaseButton>
              <BaseButton
                :disabled="!canCancel"
                variant="secondary"
                @click="cancel"
              >
                {{ t('lens.chat.cancelRun') }}
              </BaseButton>
            </div>
          </div>
        </footer>
      </main>
    </div>
  </AppLayout>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import AppLayout from '@/components/layout/AppLayout.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { useToast } from '@/composables/useToast'
import apiConfig from '@/config/api'
import {
  cancelRun,
  createRun,
  createSession,
  getRun,
  listAssistants,
  listMessages,
  listSessions
} from '@/api/lens'

import { formatDateTime } from './format'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { showError, showInfo, showSuccess, showWarning } = useToast()

const assistants = ref([])
const sessions = ref([])
const messages = ref([])
const selectedAssistantUuid = ref('')
const selectedSessionUuid = ref('')
const question = ref('')
const partialAnswer = ref('')
const streamError = ref('')
const streamEvents = ref([])
const currentRun = ref(null)
const runInline = ref(false)
const loading = ref({ run: false })
const streamController = ref(null)
const revealQueue = ref('')
const revealTimer = ref(null)
const timelineOpen = ref(false)
const seenActivityKeys = new Set()
const seenStepEventCounts = new Map()

const selectedAssistant = computed(
  () =>
    assistants.value.find(
      (item) => item.uuid === selectedAssistantUuid.value
    ) || null
)
const canCancel = computed(() =>
  ['queued', 'running', 'streaming'].includes(currentRun.value?.status)
)
const isRunActive = computed(() =>
  ['queued', 'running', 'streaming'].includes(currentRun.value?.status)
)
const showLiveAnswer = computed(
  () => isRunActive.value || partialAnswer.value || streamError.value
)
const showCursor = computed(
  () => isRunActive.value && !streamError.value && partialAnswer.value
)
const liveStatusText = computed(() => {
  if (currentRun.value?.status === 'streaming') {
    return t('lens.chat.generating')
  }
  if (currentRun.value?.status === 'running') {
    return t('lens.chat.running')
  }
  return t('lens.chat.waiting')
})
const activityEvents = computed(() =>
  streamEvents.value
    .filter((event) => event.activity)
    .slice(-5)
    .reverse()
)
const currentActivityText = computed(() => {
  const current = activityEvents.value[0]
  if (!current) {
    return t('lens.chat.thinking')
  }
  return activityTitle(current)
})

function authHeaders() {
  const token = localStorage.getItem('access_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function pushStreamEvent(event) {
  streamEvents.value.push({
    id: `${Date.now()}-${streamEvents.value.length}`,
    ...event
  })
}

function resetStreamState() {
  partialAnswer.value = ''
  revealQueue.value = ''
  stopRevealTimer()
  streamError.value = ''
  streamEvents.value = []
  timelineOpen.value = false
  seenActivityKeys.clear()
  seenStepEventCounts.clear()
}

function activityTitle(event) {
  if (!event.activity) {
    return event.label
  }
  const key = `lens.chat.activity.${event.activity}`
  const translated = t(key)
  return translated === key ? event.label : translated
}

function activityDetail(event) {
  const raw = event.agentEvent || event.message || ''
  return raw
    .replace(/^\[[^\]]+\] - /, '')
    .split('\n')
    .slice(0, 2)
    .join(' · ')
}

function pushAgentActivity(item, fallbackTs, fallbackStatus) {
  if (!item?.message && !item?.agent_event) {
    return
  }
  const key = item.agent_event || item.message
  if (seenActivityKeys.has(key)) {
    return
  }
  seenActivityKeys.add(key)
  pushStreamEvent({
    label: t('lens.chat.events.agentActivity'),
    status: fallbackStatus || 'running',
    message: item.message || item.agent_event,
    agentEvent: item.agent_event,
    activity: item.activity || 'running',
    ts: fallbackTs || new Date().toISOString()
  })
}

function stopRevealTimer() {
  if (revealTimer.value) {
    window.clearInterval(revealTimer.value)
    revealTimer.value = null
  }
}

function flushRevealQueue() {
  if (revealQueue.value) {
    partialAnswer.value += revealQueue.value
    revealQueue.value = ''
  }
  stopRevealTimer()
}

function startRevealTimer() {
  if (revealTimer.value) {
    return
  }
  revealTimer.value = window.setInterval(() => {
    if (!revealQueue.value) {
      stopRevealTimer()
      return
    }
    const nextChunk = revealQueue.value.slice(0, 4)
    revealQueue.value = revealQueue.value.slice(nextChunk.length)
    partialAnswer.value += nextChunk
  }, 18)
}

function appendAnswerDelta(content) {
  revealQueue.value += content
  startRevealTimer()
}

async function bootstrap() {
  try {
    assistants.value = await listAssistants()
    const current =
      assistants.value.find((item) => item.slug === route.params.slug) ||
      assistants.value[0]
    if (!current) {
      return
    }
    selectedAssistantUuid.value = current.uuid
    await loadSessions()
  } catch {
    showError('加载 Lens chat 失败。')
  }
}

async function loadSessions(selectUuid = '') {
  if (!selectedAssistant.value) {
    return
  }
  sessions.value = await listSessions(selectedAssistant.value.slug)
  let targetUuid = selectUuid || route.query.session || sessions.value[0]?.uuid
  if (!targetUuid) {
    const created = await createNewSession(false)
    targetUuid = created?.uuid
  }
  if (targetUuid) {
    await selectSession({ uuid: targetUuid }, false)
  }
}

async function createNewSession(notify = true) {
  if (!selectedAssistant.value) {
    return null
  }
  const session = await createSession({
    assistant_uuid: selectedAssistant.value.uuid,
    title: `${selectedAssistant.value.name} 查询`
  })
  sessions.value = [session, ...sessions.value]
  selectedSessionUuid.value = session.uuid
  messages.value = []
  currentRun.value = null
  router.replace({ query: { session: session.uuid } })
  if (notify) {
    showSuccess('已创建会话。')
  }
  return session
}

async function selectSession(session, updateRoute = true) {
  selectedSessionUuid.value = session.uuid
  messages.value = await listMessages(session.uuid)
  resetStreamState()
  if (updateRoute) {
    router.replace({ query: { session: session.uuid } })
  }
}

async function readSse(runUuid) {
  streamController.value?.abort()
  const controller = new AbortController()
  streamController.value = controller

  const response = await fetch(
    `${apiConfig.apiBaseUrl}/lens/runs/${runUuid}/stream/`,
    {
      headers: { Accept: 'text/event-stream', ...authHeaders() },
      signal: controller.signal
    }
  )
  if (!response.ok || !response.body) {
    throw new Error('SSE failed')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let streamDone = false

  while (!streamDone) {
    const { done, value } = await reader.read()
    if (done) {
      streamDone = true
      continue
    }
    buffer += decoder.decode(value, { stream: true })
    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      const raw = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      boundary = buffer.indexOf('\n\n')
      const dataLine = raw
        .split('\n')
        .find((line) => line.startsWith('data: '))
      if (dataLine) {
        handleEvent(JSON.parse(dataLine.slice(6)))
      }
    }
  }
}

function handleEvent(event) {
  if (event.type === 'sync' || event.type === 'status') {
    currentRun.value = { ...currentRun.value, status: event.status }
    if (event.type === 'sync') {
      event.steps?.forEach((step) => handleStepEvent(step, event.ts))
    }
    pushStreamEvent({
      label: t(`lens.chat.events.${event.type}`),
      status: event.status,
      message: event.status,
      ts: event.ts
    })
  }
  if (event.type === 'sync' && event.content) {
    flushRevealQueue()
    partialAnswer.value = event.content
  }
  if (event.type === 'step') {
    handleStepEvent(event, event.ts)
  }
  if (event.type === 'token') {
    appendAnswerDelta(event.content)
  }
  if (event.type === 'ping') {
    if (!activityEvents.value.length) {
      pushStreamEvent({
        label: t('lens.chat.events.ping'),
        status: currentRun.value?.status || 'processing',
        message: t('lens.chat.waitingForResult'),
        ts: event.ts
      })
    }
  }
  if (event.type === 'error') {
    streamError.value =
      event.error?.message || event.error || t('lens.chat.events.error')
    pushStreamEvent({
      label: t('lens.chat.events.error'),
      status: 'failed',
      message: streamError.value,
      ts: event.ts
    })
  }
}

function handleStepEvent(event, ts) {
  const events = event.detail?.events || []
  const stepKey = event.sequence || event.step || 'step'
  const seenCount = seenStepEventCounts.get(stepKey) || 0
  const newEvents = events.slice(seenCount)
  seenStepEventCounts.set(stepKey, events.length)

  newEvents.forEach((item) => {
    pushAgentActivity(item, ts, event.status)
  })

  if (!newEvents.length && seenCount > 0) {
    return
  }

  const timelineItems = newEvents.length
    ? newEvents
    : [{ message: event.step }]
  timelineItems.forEach((item) => {
    pushStreamEvent({
      label: t('lens.chat.events.step', { step: event.step }),
      status: event.status,
      message: item.message || item.agent_event || event.step,
      agentEvent: item.agent_event,
      activity: item.activity,
      ts
    })
  })
}

async function submit() {
  loading.value.run = true
  resetStreamState()
  try {
    const shouldRunInline = Boolean(runInline.value)
    const run = await createRun(selectedSessionUuid.value, {
      question: question.value,
      run_inline: shouldRunInline,
      enqueue: !shouldRunInline
    })
    currentRun.value = run
    pushStreamEvent({
      label: t('lens.chat.events.submitted'),
      status: run.status,
      message: run.uuid,
      ts: new Date().toISOString()
    })
    await readSse(run.uuid)
    flushRevealQueue()
    currentRun.value = await getRun(run.uuid)
    await selectSession({ uuid: selectedSessionUuid.value }, false)
    question.value = ''
    showInfo(t('lens.chat.runSubmitted'))
  } catch {
    showError(t('lens.chat.submitFailed'))
  } finally {
    loading.value.run = false
  }
}

async function cancel() {
  if (!currentRun.value) {
    return
  }
  streamController.value?.abort()
  currentRun.value = await cancelRun(currentRun.value.uuid)
  showWarning('Run 已中止。')
}

watch(selectedAssistantUuid, async () => {
  if (selectedAssistant.value) {
    router.replace(`/lens/assistants/${selectedAssistant.value.slug}/chat`)
    await loadSessions()
  }
})

onMounted(bootstrap)
onBeforeUnmount(() => {
  streamController.value?.abort()
  stopRevealTimer()
})
</script>

<style scoped>
.chat-shell {
  @apply flex min-h-[720px] flex-col rounded-lg border border-gray-200;
  @apply bg-white;
}

.stream-card {
  @apply max-w-3xl rounded-lg border border-gray-200 bg-white px-4 py-3;
}

.activity-card {
  @apply max-w-3xl rounded-lg border border-blue-100 bg-white px-4 py-3;
}

.activity-item {
  @apply flex items-start justify-between gap-3 rounded-md bg-gray-50 px-3 py-2;
}

.timeline-message {
  @apply mt-2 whitespace-pre-wrap text-xs leading-5 text-gray-700;
}

.stream-cursor {
  @apply ml-0.5 inline-block h-4 w-1 translate-y-0.5 bg-blue-500;
  animation: cursor-blink 1s steps(2, start) infinite;
}

.typing-dots {
  @apply inline-flex items-center gap-1;
}

.typing-dots span {
  @apply h-1.5 w-1.5 rounded-full bg-gray-400;
  animation: typing-dot 1.2s ease-in-out infinite;
}

.typing-dots span:nth-child(2) {
  animation-delay: 0.15s;
}

.typing-dots span:nth-child(3) {
  animation-delay: 0.3s;
}

@keyframes cursor-blink {
  0%,
  45% {
    opacity: 1;
  }
  46%,
  100% {
    opacity: 0;
  }
}

@keyframes typing-dot {
  0%,
  80%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }
  40% {
    opacity: 1;
    transform: translateY(-2px);
  }
}
</style>
