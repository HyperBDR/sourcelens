<template>
  <div class="lens-chat-page">
    <Transition
      enter-active-class="transition-opacity duration-200"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition-opacity duration-150"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div
        v-if="sidebarOpen && isMobile"
        class="fixed inset-0 z-20 bg-[#2a2722]/35"
        @click="sidebarOpen = false"
      />
    </Transition>

    <aside
      class="sidebar"
      :class="[
        sidebarOpen && isMobile ? 'sidebar-open' : '',
        sidebarCollapsedActive ? 'sidebar-collapsed' : 'sidebar-expanded'
      ]"
    >
      <div class="side-head">
        <div
          class="sidebar-brand"
          :class="sidebarCollapsedActive ? 'sidebar-brand-collapsed' : ''"
        >
          <router-link
            v-if="!sidebarCollapsedActive"
            to="/dashboard"
            class="sidebar-brand-link"
            @click="isMobile && (sidebarOpen = false)"
          >
            <BrandLogo
              :variant="sidebarLogoVariant"
              :wrapperClass="sidebarLogoWrapperClass"
            />
          </router-link>
          <button
            v-else
            type="button"
            class="sidebar-brand-link"
            :aria-label="t('common.expand')"
            @click="sidebarCollapsed = false"
          >
            <BrandLogo
              :variant="sidebarLogoVariant"
              :wrapperClass="sidebarLogoWrapperClass"
            />
          </button>
          <button
            v-if="!isMobile"
            class="sidebar-collapse-btn"
            type="button"
            :aria-label="
              sidebarCollapsedActive
                ? t('common.expand')
                : t('common.collapse')
            "
            @click="sidebarCollapsed = !sidebarCollapsed"
          >
            <PanelLeftClose
              v-if="!sidebarCollapsedActive"
              :size="20"
              :stroke-width="2.1"
              aria-hidden="true"
            />
            <PanelLeftOpen
              v-else
              :size="20"
              :stroke-width="2.1"
              aria-hidden="true"
            />
          </button>
          <button
            v-else
            class="sidebar-collapse-btn"
            type="button"
            :aria-label="t('common.close')"
            @click="sidebarOpen = false"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.25"
              aria-hidden="true"
            >
              <path
                d="M6 18L18 6M6 6l12 12"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>
        </div>

        <button
          class="new-chat-btn"
          :class="sidebarCollapsedActive ? 'new-chat-btn-collapsed' : ''"
          type="button"
          @click="createNewSession"
        >
          <Plus :size="18" :stroke-width="2.25" aria-hidden="true" />
          <span v-if="!sidebarCollapsedActive || isMobile">
            {{ t('lens.chat.newSession') }}
          </span>
        </button>
      </div>

      <div class="side-scroll">
        <section
          v-if="!sidebarCollapsedActive || isMobile"
          class="sessions-section"
        >
          <div
            class="sessions-head"
          >
            <h2>{{ t('lens.chat.sessions') }}</h2>
          </div>
          <div class="sessions-list">
            <button
              v-for="session in sessions"
              :key="session.uuid"
              type="button"
              class="session-item"
              :class="[
                selectedSessionUuid === session.uuid ? 'session-item-active' : '',
              ]"
              :title="session.title || t('lens.chat.untitledSession')"
              @click="selectSession(session)"
            >
              <div class="min-w-0">
                <div class="session-title">
                  {{ session.title || t('lens.chat.untitledSession') }}
                </div>
              </div>
            </button>
          </div>
        </section>
      </div>

      <div class="sidebar-footer">
        <div ref="dockMenuRef" class="dock-menu-wrap">
          <button
            class="dock-trigger"
            :class="[
              dockMenuOpen ? 'dock-trigger-open' : '',
              sidebarCollapsedActive ? 'dock-trigger-collapsed' : ''
            ]"
            type="button"
            @click="dockMenuOpen = !dockMenuOpen"
          >
            <div class="dock-avatar" :class="avatarBgColor">
              <span>{{ userInitials }}</span>
            </div>
            <div
              v-if="!sidebarCollapsedActive || isMobile"
              class="min-w-0 flex-1 text-left"
            >
              <div class="truncate text-sm font-medium text-ink-900">
                {{ displayName }}
              </div>
              <div class="truncate text-xs text-ink-500">
                {{ t('platforms.workspace') }}
              </div>
            </div>
            <svg
              v-if="!sidebarCollapsedActive || isMobile"
              class="h-4 w-4 shrink-0 text-ink-500 transition-transform"
              :class="{ 'rotate-180': dockMenuOpen }"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              aria-hidden="true"
            >
              <path
                d="m6 9 6 6 6-6"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>

          <Transition
            enter-active-class="transition ease-out duration-100"
            enter-from-class="transform opacity-0 translate-y-1 scale-95"
            enter-to-class="transform opacity-100 translate-y-0 scale-100"
            leave-active-class="transition ease-in duration-75"
            leave-from-class="transform opacity-100 translate-y-0 scale-100"
            leave-to-class="transform opacity-0 translate-y-1 scale-95"
          >
            <div v-if="dockMenuOpen" class="dock-menu">
              <div class="dock-section border-b border-line">
                <AssistantSwitcher mode="flyout" />
              </div>

              <div v-if="userStore.userHasFeature('admin_console')" class="dock-section">
                <router-link
                  to="/management/users"
                  class="dock-link"
                  @click="dockMenuOpen = false"
                >
                  <span class="truncate">{{ t('platforms.adminConsole') }}</span>
                </router-link>
              </div>

              <div class="dock-section border-t border-line">
                <button
                  type="button"
                  class="dock-link"
                  @click="openSettings"
                >
                  <span class="truncate">{{ t('common.settings') }}</span>
                </button>
                <button type="button" class="dock-link" @click="handleLogout">
                  <span class="truncate">{{ t('common.logout') }}</span>
                </button>
              </div>
            </div>
          </Transition>
        </div>
      </div>
    </aside>

    <main class="main-shell">
      <div ref="scrollRef" class="thread-scroll">
        <div v-if="!selectedAssistantUuid" class="thread-loading">
          <BaseLoading />
        </div>
        <div v-else class="thread">
          <div
            v-for="message in messages"
            :key="message.uuid"
            class="message-row"
            :class="message.role === 'user' ? 'message-row-user' : 'message-row-assistant'"
          >
            <div
              class="message-avatar"
              :class="[message.role, message.role === 'user' ? avatarBgColor : '']"
            >
              <Smile v-if="message.role === 'user'" :size="17" :stroke-width="2" />
              <img
                v-else
                src="/brand/logo_transparent.png"
                alt="SourceLens"
                class="h-[20px] w-[20px] object-contain"
              />
            </div>

            <div class="message-body">
              <div class="message-card" :class="message.role">
                <div v-if="message.role === 'assistant'" class="message-markdown">
                  <MarkdownRenderer :content="message.content || '（空）'" />
                </div>
                <div v-else class="message-text">
                  {{ message.content || '（空）' }}
                </div>
              </div>

              <div class="message-time" :class="message.role">
                {{ formatTime(message.created_at) }}
              </div>

              <div
                v-if="message.role === 'assistant'"
                class="message-actions"
              >
                <button
                  type="button"
                  class="icon-btn"
                  @click="copyMessage(message)"
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    aria-hidden="true"
                  >
                    <rect x="9" y="9" width="13" height="13" rx="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                  </svg>
                </button>
                <button
                  type="button"
                  class="icon-btn"
                  @click="retryLastQuestion"
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    aria-hidden="true"
                  >
                    <path
                      d="M3 12a9 9 0 1 0 3-6.7L3 8"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                    <path
                      d="M3 3v5h5"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          <article v-if="showLiveAnswer" class="live-card">
            <div class="card-head">
              <div class="card-title">ASSISTANT</div>
              <div v-if="isRunActive" class="card-state">
                {{ liveStatusText }}
              </div>
            </div>

            <div v-if="partialAnswer || streamError" class="live-text">
              {{ partialAnswer || streamError }}
              <span v-if="showCursor" class="stream-cursor" />
            </div>
            <div v-else class="live-thinking">
              <span>{{ t('lens.chat.thinking') }}</span>
              <span class="typing-dots" aria-hidden="true">
                <span />
                <span />
                <span />
              </span>
            </div>
          </article>
        </div>
      </div>

      <div class="composer-wrap">
        <div class="composer-inner">
          <div class="composer-shell">
            <div class="composer">
              <button
                class="composer-icon-btn"
                type="button"
                :aria-label="t('lens.chat.newSession')"
                @click="createNewSession"
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                  aria-hidden="true"
                >
                  <path d="M12 5v14M5 12h14" stroke-linecap="round" />
                </svg>
              </button>
              <input
                ref="composerRef"
                v-model="question"
                class="composer-input"
                :placeholder="t('lens.chat.questionPlaceholder')"
              />
              <button
                class="composer-action-btn"
                :class="isRunActive ? 'composer-action-btn-stop' : ''"
                type="button"
                :disabled="!selectedSessionUuid || (!question.trim() && !isRunActive)"
                :aria-label="isRunActive ? t('common.stop') : t('common.submit')"
                @click="handlePrimaryAction"
              >
                <svg
                  v-if="!isRunActive"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                  aria-hidden="true"
                >
                  <path
                    d="M12 19V5M5 12l7-7 7 7"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
                <svg
                  v-else
                  viewBox="0 0 24 24"
                  fill="currentColor"
                  aria-hidden="true"
                >
                  <rect x="7" y="7" width="10" height="10" rx="2.2" />
                </svg>
              </button>
            </div>
          </div>

          <p class="disclaimer">
            {{ t('lens.chat.disclaimer') || '回答由 AI 生成，请自行核实关键信息。' }}
          </p>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import {
  computed,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
  nextTick
} from 'vue'
import { PanelLeftClose, PanelLeftOpen, Plus, Smile } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import MarkdownRenderer from '@/components/ui/MarkdownRenderer.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import AssistantSwitcher from '@/components/lens/AssistantSwitcher.vue'
import { useToast } from '@/composables/useToast'
import apiConfig from '@/config/api'
import { useUiStore } from '@/store/ui'
import { useUserStore } from '@/store/user'
import {
  cancelRun,
  createRun,
  createSession,
  getRun,
  listAssistants,
  listMessages,
  listSessions
} from '@/api/lens'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { showError, showInfo, showSuccess, showWarning } = useToast()
const userStore = useUserStore()
const uiStore = useUiStore()

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
const loading = ref({ run: false })
const streamController = ref(null)
const revealQueue = ref('')
const revealTimer = ref(null)
const sidebarOpen = ref(false)
const sidebarCollapsed = ref(false)
const dockMenuOpen = ref(false)
const composerRef = ref(null)
const scrollRef = ref(null)
const dockMenuRef = ref(null)
const seenActivityKeys = new Set()
const seenStepEventCounts = new Map()

const selectedAssistant = computed(
  () =>
    assistants.value.find(
      (item) => item.uuid === selectedAssistantUuid.value
    ) || null
)

const displayName = computed(() => {
  const userInfo = userStore.userInfo
  if (!userInfo) return 'User'
  if (userInfo.display_name) return userInfo.display_name
  if (userInfo.first_name && userInfo.last_name) {
    return `${userInfo.first_name} ${userInfo.last_name}`
  }
  if (userInfo.first_name) return userInfo.first_name
  return userInfo.username || 'User'
})

const userInitials = computed(() => {
  const name = displayName.value.trim()
  return name.charAt(0).toUpperCase() || 'U'
})

const avatarBgColor = computed(() => {
  const colors = [
    'bg-blue-500',
    'bg-indigo-500',
    'bg-emerald-500',
    'bg-rose-500',
    'bg-amber-500',
    'bg-cyan-500'
  ]
  const charCode = userInitials.value.charCodeAt(0)
  return colors[charCode % colors.length]
})

const sidebarLogoVariant = computed(() =>
  sidebarCollapsed.value && !isMobile.value ? 'mark' : 'wordmark'
)

const sidebarLogoWrapperClass = computed(() =>
  sidebarCollapsed.value && !isMobile.value
    ? 'sidebar-brand-logo origin-center scale-[0.72]'
    : 'sidebar-brand-logo origin-left'
)

const sidebarCollapsedActive = computed(
  () => sidebarCollapsed.value && !isMobile.value
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

const isMobile = computed(() => {
  if (typeof window === 'undefined') return false
  return window.innerWidth < 1024
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
  seenActivityKeys.clear()
  seenStepEventCounts.clear()
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
    nextTick(scrollToBottom)
  }, 18)
}

function appendAnswerDelta(content) {
  revealQueue.value += content
  startRevealTimer()
}

function scrollToBottom() {
  const el = scrollRef.value
  if (!el) return
  el.scrollTop = el.scrollHeight
}

const openSettings = () => {
  uiStore.openSettings()
  dockMenuOpen.value = false
}

async function handleLogout() {
  try {
    await userStore.logout()
  } catch {
    // Fall through to local redirect.
  } finally {
    dockMenuOpen.value = false
    await router.push('/login')
  }
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

    if (current.slug !== route.params.slug) {
      await router.replace(`/lens/assistants/${current.slug}/chat`)
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
  router.replace({
    path: route.path,
    query: { session: session.uuid }
  })

  if (notify) {
    showSuccess('已创建会话。')
  }

  return session
}

async function handlePrimaryAction() {
  if (isRunActive.value) {
    await cancel()
    return
  }
  await submit()
}

async function selectSession(session, updateRoute = true) {
  selectedSessionUuid.value = session.uuid
  messages.value = await listMessages(session.uuid)
  resetStreamState()
  if (updateRoute) {
    router.replace({
      path: route.path,
      query: { session: session.uuid }
    })
  }
  await nextTick(scrollToBottom)
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
    const run = await createRun(selectedSessionUuid.value, {
      question: question.value,
      run_inline: false,
      enqueue: true
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
    await nextTick(scrollToBottom)
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
  showWarning(t('lens.chat.runStopped'))
}

async function copyMessage(message) {
  try {
    await navigator.clipboard.writeText(message.content || '')
    showSuccess('已复制消息。')
  } catch {
    showWarning('复制失败。')
  }
}

function retryLastQuestion() {
  const lastUserMessage = [...messages.value].reverse().find(
    (message) => message.role === 'user'
  )
  if (!lastUserMessage) {
    return
  }
  question.value = lastUserMessage.content || ''
  nextTick(() => {
    composerRef.value?.focus()
  })
}

function formatTime(isoString) {
  if (!isoString) return ''
  return new Date(isoString).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  })
}

function handleOutsideClick(event) {
  const target = event.target
  if (dockMenuRef.value && !dockMenuRef.value.contains(target)) {
    dockMenuOpen.value = false
  }
}

watch(
  () => route.params.slug,
  () => {
    bootstrap()
  },
  { immediate: true }
)

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
  if (window.innerWidth < 1024) {
    sidebarOpen.value = false
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleOutsideClick)
  streamController.value?.abort()
  stopRevealTimer()
})
</script>

<style scoped>
.lens-chat-page {
  @apply flex h-screen w-full overflow-hidden;
  background: #f5f3ee;
  color: #2a2722;
}

.sidebar {
  @apply flex h-full flex-shrink-0 flex-col border-r transition-all duration-300 ease-in-out;
  background: #f5f3ee;
  border-color: #e6e1d6;
}

.sidebar-expanded {
  @apply w-[264px];
}

.sidebar-collapsed {
  @apply w-[64px];
}

.side-head {
  @apply px-3 pt-4 pb-3;
}

.sidebar-brand {
  @apply flex items-center justify-between gap-2 px-1 pb-4;
}

.sidebar-brand-collapsed {
  @apply flex-col items-center justify-start gap-2;
}

.sidebar-brand-collapsed .sidebar-brand-link {
  @apply flex-none flex w-full items-center justify-center;
}

.sidebar-brand-collapsed .sidebar-collapse-btn {
  @apply self-center;
}

.sidebar-brand-link {
  @apply min-w-0 flex-1 overflow-hidden border-0 bg-transparent p-0 text-left;
}

.sidebar-brand-logo {
  @apply max-w-full;
}

.sidebar-collapse-btn {
  @apply flex h-10 w-10 shrink-0 items-center justify-center rounded-md transition-colors;
  color: #46423a;
}

.sidebar-collapse-btn:hover {
  background: #efebe2;
}

.sidebar-collapse-btn svg {
  @apply h-5 w-5;
}

.new-chat-btn {
  @apply flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors;
  color: #46423a;
}

.new-chat-btn:hover {
  background: #efebe2;
}

.new-chat-btn svg {
  @apply h-4 w-4 shrink-0;
}

.new-chat-btn-collapsed {
  @apply justify-center px-0;
}

.side-scroll {
  @apply flex-1 overflow-y-auto px-3 pb-4 pt-3;
}

.sessions-head {
  @apply px-1 pb-2;
}

.sessions-head h2 {
  @apply text-[11px] font-semibold tracking-wide;
  color: #928b7d;
}

.sessions-list {
  @apply space-y-1;
}

.session-item {
  @apply flex w-full items-center gap-3 rounded-xl px-3 py-2 text-left transition-colors;
}

.session-item:hover {
  background: #efebe2;
}

.session-item-active {
  background: #ebe4d8;
}

.session-title {
  @apply truncate text-sm font-medium;
  color: #2a2722;
}

.main-shell {
  @apply relative flex min-w-0 flex-1 flex-col overflow-hidden;
  background: #fbfaf7;
}

.thread-scroll {
  @apply min-h-0 flex-1 overflow-y-auto;
}

.thread-loading {
  @apply flex h-full items-center justify-center px-6;
}

.thread {
  @apply mx-auto w-full max-w-[900px] px-6 py-8;
  padding-bottom: 240px;
}

.message-row {
  @apply mb-9 flex items-start gap-4;
}

.message-row-user {
  @apply justify-end;
}

.message-row-user .message-avatar {
  order: 2;
}

.message-avatar {
  @apply flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] text-xs font-semibold;
}

.message-avatar.user {
  color: #fff;
}

.message-avatar.assistant {
  background: #ffffff;
  border: 1px solid #e6e1d6;
}

.message-body {
  @apply min-w-0 flex-1;
}

.message-row-user .message-body {
  @apply max-w-[640px];
}

.message-card {
  @apply rounded-lg border px-4 py-3 shadow-none;
}

.message-card.user {
  border-color: #b9cdfa;
  background: #eef4fe;
}

.message-card.assistant {
  border-color: #e6e1d6;
  background: #ffffff;
}

.message-time {
  @apply mt-1 text-xs;
  color: #c2bbb0;
}

.message-time.user {
  @apply text-right;
}

.message-markdown {
  @apply mt-2;
}

.message-markdown :deep(.markdown-content) {
  @apply max-w-none;
  color: #46423a;
}

.message-markdown :deep(.markdown-content h1),
.message-markdown :deep(.markdown-content h2),
.message-markdown :deep(.markdown-content h3),
.message-markdown :deep(.markdown-content h4) {
  color: #2a2722;
}

.message-markdown :deep(.markdown-content p) {
  @apply mb-3 text-[16px] leading-7;
  color: #46423a;
}

.message-markdown :deep(.markdown-content ul),
.message-markdown :deep(.markdown-content ol) {
  @apply mb-3 pl-5;
}

.message-markdown :deep(.markdown-content li) {
  @apply mb-2 text-[16px] leading-7;
  color: #46423a;
}

.message-markdown :deep(.markdown-content code) {
  background: #eef4fe;
  color: #0e278c;
}

.message-text {
  @apply mt-2 whitespace-pre-wrap text-[16px] leading-7;
  color: #2a2722;
}

.message-actions {
  @apply mt-3 flex gap-1;
}

.icon-btn {
  @apply flex h-[30px] w-[30px] items-center justify-center rounded-md transition-colors;
  color: #928b7d;
}

.icon-btn:hover {
  background: #efebe2;
  color: #46423a;
}

.icon-btn svg {
  @apply h-4 w-4;
}

.live-card,
.activity-card,
.timeline-card {
  @apply mb-9 max-w-[900px] rounded-lg border bg-white px-4 py-3;
  border-color: #e6e1d6;
}

.card-head {
  @apply flex items-center justify-between gap-3;
}

.card-title,
.card-heading {
  @apply text-xs font-semibold uppercase tracking-wide;
  color: #928b7d;
}

.card-state,
.card-caption {
  @apply text-xs;
  color: #928b7d;
}

.live-text {
  @apply mt-2 whitespace-pre-wrap text-[16px] leading-7;
  color: #2a2722;
}

.live-thinking {
  @apply mt-2 flex items-center gap-2 text-sm;
  color: #6b6559;
}

.typing-dots {
  @apply inline-flex items-center gap-1;
}

.typing-dots span {
  @apply h-1.5 w-1.5 rounded-full;
  background: #928b7d;
  animation: typing-dot 1.2s ease-in-out infinite;
}

.typing-dots span:nth-child(2) {
  animation-delay: 0.15s;
}

.typing-dots span:nth-child(3) {
  animation-delay: 0.3s;
}

.stream-cursor {
  @apply ml-0.5 inline-block h-4 w-1 translate-y-0.5;
  background: #2b4ee6;
  animation: cursor-blink 1s steps(2, start) infinite;
}

.activity-list {
  @apply mt-3 space-y-2;
}

.activity-item {
  @apply flex items-start justify-between gap-3 rounded-md px-3 py-2;
  background: #fbfaf7;
}

.activity-title {
  @apply text-sm font-medium;
  color: #2a2722;
}

.activity-detail {
  @apply mt-1 truncate text-xs;
  color: #928b7d;
}

.activity-time,
.timeline-time {
  @apply shrink-0 text-xs;
  color: #928b7d;
}

.timeline-toggle {
  @apply flex w-full items-center justify-between gap-3 text-left;
}

.timeline-list {
  @apply mt-3;
}

.timeline-list > * + * {
  border-top: 1px solid #efebe2;
}

.timeline-item {
  @apply py-3;
}

.timeline-line {
  @apply flex flex-wrap items-center gap-2;
}

.timeline-status {
  @apply rounded-full px-2 py-0.5 text-xs font-medium;
  background: #eef4fe;
  color: #0e278c;
}

.timeline-label {
  @apply text-xs;
  color: #6b6559;
}

.timeline-message {
  @apply mt-2 whitespace-pre-wrap text-xs leading-5;
  color: #46423a;
}

.composer-wrap {
  @apply pointer-events-none absolute inset-x-0 bottom-0 z-20 px-6 pb-5;
  background: linear-gradient(
    to top,
    rgba(251, 250, 247, 0.98) 36%,
    rgba(251, 250, 247, 0.78) 72%,
    rgba(251, 250, 247, 0) 100%
  );
}

.composer-inner {
  @apply mx-auto w-full max-w-[900px];
}

.composer-shell {
  @apply pointer-events-auto rounded-[28px] border border-line bg-surface/95 px-4 py-3 shadow-[0_20px_50px_rgba(42,39,34,0.08)];
  backdrop-filter: blur(18px);
}

.composer {
  @apply flex items-center gap-3 rounded-[24px] bg-white px-3 py-2.5;
}

.composer:focus-within {
  box-shadow: 0 0 0 3px rgba(43, 78, 230, 0.12);
}

.composer-input {
  @apply h-10 flex-1 border-0 bg-transparent p-0 text-[16px] leading-6 outline-none;
  color: #2a2722;
}

.composer-input::placeholder {
  color: #928b7d;
}

.composer-icon-btn {
  @apply flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors;
  color: #46423a;
  background: #f6f3ed;
}

.composer-icon-btn:hover {
  background: #ede7de;
}

.composer-icon-btn svg {
  @apply h-5 w-5;
}

.composer-action-btn {
  @apply flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors;
  background: #111111;
  color: #fff;
}

.composer-action-btn:hover:not(:disabled) {
  background: #2a2722;
}

.composer-action-btn-stop {
  background: #111111;
}

.composer-action-btn:disabled {
  background: #e6e1d6;
  cursor: not-allowed;
}

.composer-action-btn svg {
  @apply h-[17px] w-[17px];
}

.disclaimer {
  @apply mt-3 text-center text-xs;
  color: #928b7d;
}

.sidebar-footer {
  @apply border-t border-line p-3;
}

.dock-menu-wrap {
  @apply relative;
}

.dock-trigger {
  @apply flex w-full items-center gap-3 rounded-xl border border-line bg-surface px-3 py-2 text-left shadow-sm transition-colors;
}

.dock-trigger:hover,
.dock-trigger-open {
  @apply border-primary-200 bg-primary-50;
}

.dock-trigger-collapsed {
  @apply justify-center px-0;
}

.dock-avatar {
  @apply flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white;
}

.dock-menu {
  @apply absolute bottom-full left-0 z-40 mb-2 w-full overflow-visible rounded-2xl border border-line bg-surface shadow-xl;
}

.dock-section {
  @apply border-b border-line px-3 py-3 last:border-b-0;
}

.dock-link {
  @apply flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm text-ink-700 transition-colors;
}

.dock-link:hover {
  @apply bg-line-soft text-ink-900;
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

@media (max-width: 1023px) {
  .sidebar {
    @apply fixed inset-y-0 left-0 z-30 -translate-x-full transition-transform duration-300;
    box-shadow: 0 0 40px rgba(42, 39, 34, 0.15);
  }

  .sidebar-open {
    @apply translate-x-0;
  }

  .thread {
    @apply px-4 py-6;
    padding-bottom: 260px;
  }

  .main-shell {
    padding-top: env(safe-area-inset-top);
  }

  .composer-wrap {
    @apply px-4 pb-4;
  }

  .dock-menu {
    width: 100%;
  }
}

@media (min-width: 1024px) {
  .main-shell {
    box-shadow: inset 1px 0 0 #ddd6c6;
  }
}
</style>
