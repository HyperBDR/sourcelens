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
            <div
              v-for="session in sessions"
              :key="session.uuid"
              class="session-item"
              :class="[
                deletingSessionUuid === session.uuid ? 'session-item-deleting' : selectedSessionUuid === session.uuid ? 'session-item-active' : ''
              ]"
            >
              <input
                v-if="renamingSessionUuid === session.uuid"
                v-model="renameDraft"
                class="session-rename-input"
                :placeholder="t('lens.chat.untitledSession')"
                @click.stop
                @keydown.enter.stop.prevent="saveRename(session)"
                @keydown.esc.stop="cancelRename"
                @blur="saveRename(session)"
              />
              <template v-else>
                <div
                  class="min-w-0 flex-1 cursor-pointer"
                  :title="session.title || t('lens.chat.untitledSession')"
                  @click="deletingSessionUuid !== session.uuid && selectSession(session)"
                >
                  <div class="session-title" :class="deletingSessionUuid === session.uuid ? 'opacity-40' : ''">
                    {{ session.title || t('lens.chat.untitledSession') }}
                  </div>
                </div>

                <div class="flex shrink-0 items-center gap-1">
                  <template v-if="deletingSessionUuid === session.uuid">
                    <button
                      type="button"
                      class="session-action-btn session-action-confirm"
                      :aria-label="t('common.confirm')"
                      @click.stop="doDeleteSession(session)"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
                        <path d="M20 6 9 17l-5-5" stroke-linecap="round" stroke-linejoin="round" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      class="session-action-btn session-action-cancel"
                      :aria-label="t('common.cancel')"
                      @click.stop="deletingSessionUuid = ''"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
                        <path d="M18 6 6 18M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" />
                      </svg>
                    </button>
                  </template>
                  <template v-else>
                    <button
                      type="button"
                      class="session-rename-btn"
                      :aria-label="t('lens.chat.renameSession')"
                      @click.stop="startRename(session)"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                        <path d="M12 20h9" stroke-linecap="round" stroke-linejoin="round" />
                        <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z" stroke-linecap="round" stroke-linejoin="round" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      class="session-delete-btn"
                      :aria-label="t('lens.chat.deleteSession')"
                      @click.stop="deletingSessionUuid = session.uuid"
                    >
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                        <path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" stroke-linecap="round" stroke-linejoin="round" />
                      </svg>
                    </button>
                  </template>
                </div>
              </template>
            </div>
          </div>
        </section>
      </div>

      <div class="sidebar-footer">
        <button
          v-if="isAnonymous"
          type="button"
          class="anon-login-btn"
          :class="{
            'anon-login-btn-collapsed': sidebarCollapsedActive && !isMobile
          }"
          :title="t('auth.signIn')"
          @click="requireLogin"
        >
          <LogIn :size="18" :stroke-width="2" aria-hidden="true" />
          <span v-if="!sidebarCollapsedActive || isMobile">
            {{ t('auth.signIn') }}
          </span>
        </button>
        <div v-else ref="dockMenuRef" class="dock-menu-wrap">
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
              <div
                v-if="userStore.userHasFeature('admin_console')"
                class="dock-section border-b border-line"
              >
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
      <div v-if="isMobile" class="mobile-topbar">
        <button
          type="button"
          class="sidebar-collapse-btn"
          :aria-label="t('lens.chat.sessions')"
          @click="sidebarOpen = true"
        >
          <PanelLeftOpen :size="20" :stroke-width="2.1" aria-hidden="true" />
        </button>
        <div class="mobile-topbar-title">{{ assistantName }}</div>
        <button
          type="button"
          class="sidebar-collapse-btn"
          :aria-label="t('lens.chat.newSession')"
          @click="createNewSession"
        >
          <Plus :size="20" :stroke-width="2.1" aria-hidden="true" />
        </button>
      </div>
      <header v-if="!isMobile && assistantName" class="chat-header">
        <span class="chat-header-title">{{ assistantName }}</span>
      </header>
      <div ref="scrollRef" class="thread-scroll">
        <div v-if="!booted" class="thread-loading">
          <BaseLoading />
        </div>
        <div v-else-if="!hasAssistant" class="thread-loading">
          <AssistantEmptyState :variant="emptyVariant" />
        </div>
        <div v-else class="thread">
          <div
            v-for="message in decoratedMessages"
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
              <div
                v-if="message._thinkingSteps"
                class="thinking-panel thinking-panel-done"
              >
                <button
                  type="button"
                  class="thinking-panel-header"
                  @click="toggleThinking(message.uuid)"
                >
                  <Sparkles :size="13" class="thinking-done-icon" />
                  <span class="thinking-panel-status">
                    {{
                      message.thinking.duration_seconds != null
                        ? t('lens.chat.thinkingDone', {
                            duration: formatDuration(
                              message.thinking.duration_seconds
                            ),
                            count: message._thinkingSteps.length
                          })
                        : t('lens.chat.thinkingDoneSteps', {
                            count: message._thinkingSteps.length
                          })
                    }}
                  </span>
                  <ChevronUp
                    v-if="expandedThinking.has(message.uuid)"
                    :size="13"
                    class="thinking-panel-chevron"
                  />
                  <ChevronDown v-else :size="13" class="thinking-panel-chevron" />
                </button>
                <div
                  v-if="expandedThinking.has(message.uuid)"
                  class="thinking-panel-body"
                >
                  <div
                    v-for="step in message._thinkingSteps"
                    :key="step.id"
                    class="thinking-step-item"
                  >
                    <span class="thinking-step-bullet">▸</span>
                    <span class="thinking-step-text">{{ step.message }}</span>
                    <span v-if="step.count > 1" class="thinking-step-repeat">
                      ×{{ step.count }}
                    </span>
                  </div>
                </div>
              </div>

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

          <!-- Empty-answer hint: a finished turn returned no text -->
          <div
            v-if="showRetryHint"
            class="message-row message-row-assistant"
          >
            <div class="message-avatar assistant">
              <img
                src="/brand/logo_transparent.png"
                alt="SourceLens"
                class="h-[20px] w-[20px] object-contain"
              />
            </div>
            <div class="message-body">
              <div class="retry-hint">
                <span class="retry-hint-text">
                  {{ t('lens.chat.emptyAnswerHint') }}
                </span>
                <button
                  type="button"
                  class="retry-hint-btn"
                  @click="retryLastQuestion"
                >
                  {{ t('lens.chat.retryAction') }}
                </button>
              </div>
            </div>
          </div>

          <!-- Live answer: one row / one avatar — thinking panel + streaming markdown -->
          <div
            v-if="showLiveAnswer"
            class="message-row message-row-assistant live-progress-row"
          >
            <div class="message-avatar assistant">
              <img
                src="/brand/logo_transparent.png"
                alt="SourceLens"
                class="h-[20px] w-[20px] object-contain"
              />
            </div>
            <div class="message-body">
              <div v-if="isRunActive" class="thinking-panel thinking-panel-live">
                <button
                  type="button"
                  class="thinking-panel-header"
                  @click="thinkingPanelOpen = !thinkingPanelOpen"
                >
                  <span class="live-progress-dot" />
                  <span class="thinking-panel-status">
                    <span class="thinking-panel-status-text">{{
                      latestLiveStep || latestActivityMessage || liveStatusText
                    }}</span>
                    <span
                      v-if="!latestLiveStep && !latestActivityMessage"
                      class="typing-dots"
                      aria-hidden="true"
                    >
                      <span /><span /><span />
                    </span>
                  </span>
                  <span v-if="elapsedText" class="thinking-elapsed">{{ elapsedText }}</span>
                  <span v-if="thinkingSteps.length > 0" class="thinking-step-count">
                    {{ thinkingSteps.length }}
                  </span>
                  <ChevronUp v-if="thinkingPanelOpen && (thinkingSteps.length > 0 || thinkingText)" :size="13" class="thinking-panel-chevron" />
                  <ChevronDown v-else-if="thinkingSteps.length > 0 || thinkingText" :size="13" class="thinking-panel-chevron" />
                </button>
                <div
                  v-if="thinkingPanelOpen && (thinkingSteps.length > 0 || thinkingText)"
                  ref="thinkingPanelRef"
                  class="thinking-panel-body"
                >
                  <div v-for="step in thinkingSteps" :key="step.id" class="thinking-step-item">
                    <span class="thinking-step-bullet">▸</span>
                    <span class="thinking-step-text">{{ step.message }}</span>
                    <span v-if="step.count > 1" class="thinking-step-repeat">×{{ step.count }}</span>
                  </div>
                  <div v-if="thinkingText" class="thinking-reasoning">
                    {{ thinkingText }}
                  </div>
                </div>
              </div>

              <div v-if="partialAnswer || streamError" class="message-card assistant">
                <div v-if="streamError" class="live-text">
                  {{ streamError }}
                </div>
                <div
                  v-else
                  class="message-markdown live-markdown"
                  :class="{ 'is-streaming': showCursor }"
                >
                  <MarkdownRenderer :content="partialAnswer" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="hasAssistant" class="composer-wrap">
        <div class="composer-inner">
          <div class="composer-shell">
            <div class="composer">
              <textarea
                ref="composerRef"
                v-model="question"
                class="composer-input"
                rows="1"
                :placeholder="t('lens.chat.questionPlaceholder')"
                @keydown.enter.exact.prevent="insertNewline"
                @keydown.ctrl.enter.exact.prevent="handlePrimaryAction"
                @input="autoResizeTextarea"
              />
              <button
                class="composer-action-btn"
                :class="isRunActive ? 'composer-action-btn-stop' : ''"
                type="button"
                :disabled="(!isAnonymous && !selectedSessionUuid) || (!question.trim() && !isRunActive)"
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
                  <rect x="5" y="5" width="14" height="14" rx="2.5" />
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

    <LoginModal
      :show="showLoginModal"
      @close="showLoginModal = false"
      @success="onLoginSuccess"
    />
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
import { PanelLeftClose, PanelLeftOpen, Plus, Smile, ChevronDown, ChevronUp, Sparkles, LogIn } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import MarkdownRenderer from '@/components/ui/MarkdownRenderer.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import AssistantSwitcher from '@/components/lens/AssistantSwitcher.vue'
import AssistantEmptyState from '@/components/lens/AssistantEmptyState.vue'
import LoginModal from '@/components/auth/LoginModal.vue'
import { useToast } from '@/composables/useToast'
import { useIsMobile } from '@/composables/useIsMobile'
import apiConfig from '@/config/api'
import { useUiStore } from '@/store/ui'
import { useUserStore } from '@/store/user'
import {
  cancelRun,
  createRun,
  createSession,
  deleteSession,
  getPublicAssistant,
  getRun,
  listAssistants,
  listMessages,
  listSessions,
  updateSession
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
const queuePosition = ref(null)
const currentRun = ref(null)
const loading = ref({ run: false })
const streamController = ref(null)
const sidebarOpen = ref(false)
const sidebarCollapsed = ref(false)
const deletingSessionUuid = ref('')
const renamingSessionUuid = ref('')
const renameDraft = ref('')
const dockMenuOpen = ref(false)
const composerRef = ref(null)
const scrollRef = ref(null)
const dockMenuRef = ref(null)
const seenActivityKeys = new Set()
const seenStepEventCounts = new Map()
const thinkingPanelOpen = ref(false)
const thinkingPanelRef = ref(null)
const thinkingText = ref('')
const elapsedSeconds = ref(0)
let elapsedTimer = null
let revealTimer = null
const REVEAL_INTERVAL_MS = 300

const publicAssistant = ref(null)
const showLoginModal = ref(false)
// False until the current bootstrap settles, so the view can distinguish
// "still loading" from "loaded, but no assistant to show".
const booted = ref(false)

const selectedAssistant = computed(
  () =>
    assistants.value.find(
      (item) => item.uuid === selectedAssistantUuid.value
    ) || null
)

const isAnonymous = computed(() => !userStore.isAuthenticated)

const hasAssistant = computed(() =>
  isAnonymous.value ? !!publicAssistant.value : !!selectedAssistantUuid.value
)

const emptyVariant = computed(() =>
  userStore.userHasFeature('admin_console') ? 'admin' : 'visitor'
)

const assistantName = computed(
  () => selectedAssistant.value?.name || publicAssistant.value?.name || ''
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
  if (currentRun.value?.status === 'queued') {
    if (queuePosition.value === null) return t('lens.chat.queued')
    if (queuePosition.value === 0) return t('lens.chat.queuedNext')
    return t('lens.chat.queuedPosition', { position: queuePosition.value })
  }
  return t('lens.chat.waiting')
})

const activityEvents = computed(() =>
  streamEvents.value
    .filter((event) => event.activity)
    .slice(-5)
    .reverse()
)

function toolLabel(name) {
  const map = {
    search_workspace: t('lens.chat.activity.searchWorkspace'),
    read_workspace_file: t('lens.chat.activity.readFile'),
    find_files: t('lens.chat.activity.findFiles'),
    git_log: t('lens.chat.activity.gitLog'),
    git_diff: t('lens.chat.activity.gitDiff'),
    summarize_recent_changes: t('lens.chat.activity.summarizeChanges'),
    write_file: t('lens.chat.activity.writingFile'),
    read_file: t('lens.chat.activity.readFile'),
    edit_file: t('lens.chat.activity.editingFile'),
    ls: t('lens.chat.activity.listFiles'),
    write_todos: t('lens.chat.activity.planningTasks'),
    task: t('lens.chat.activity.delegatingTask'),
  }
  return map[name] || t('lens.chat.activity.callingTool', { name })
}

function _friendlyActivityMessage(event) {
  const agentEvent = event.agentEvent || ''
  const activity = event.activity || ''
  if (agentEvent.startsWith('tool.')) {
    const parts = agentEvent.split('.')
    const action = parts[2]
    if (action === 'done' || action === 'denied') return null
    return toolLabel(parts[1])
  }
  if (activity === 'thinking') return t('lens.chat.activity.thinking')
  if (activity === 'loading_resources') return t('lens.chat.activity.loadingResources')
  return null
}

// Rich step label: the tool/model action plus the backend-provided summary
// (search query, result counts, file + line range, model decision).
function _liveStepLabel(event) {
  const agentEvent = event.agentEvent || ''
  const activity = event.activity || ''
  const summary = event.summary || ''
  const trim = (s) => s.replace(/[.…\s]+$/, '')
  if (agentEvent.startsWith('tool.')) {
    const parts = agentEvent.split('.')
    const name = parts[1]
    const action = parts[2]
    if (action === 'directory' || action === 'denied') return null
    // a read reports the same file + range on start and done — keep one line
    if (action === 'done' && name === 'read_workspace_file') return null
    return summary ? `${trim(toolLabel(name))} · ${summary}` : toolLabel(name)
  }
  if (agentEvent === 'llm.response') {
    return summary
      ? `${trim(t('lens.chat.activity.thinking'))} · ${summary}`
      : null
  }
  if (activity === 'loading_resources') {
    return t('lens.chat.activity.loadingResources')
  }
  return null
}

const latestActivityMessage = computed(() => {
  for (const event of activityEvents.value) {
    const msg = _friendlyActivityMessage(event)
    if (msg) return msg
  }
  return null
})

const allLiveSteps = computed(() => {
  const grouped = []
  for (const e of streamEvents.value) {
    const msg = _liveStepLabel(e)
    if (!msg) continue
    const last = grouped[grouped.length - 1]
    if (last && last.message === msg) {
      last.count++
    } else {
      grouped.push({ id: e.id, message: msg, count: 1 })
    }
  }
  return grouped
})

// Paced reveal: surface buffered steps one at a time for a streaming feel.
const revealedCount = ref(0)
const thinkingSteps = computed(() =>
  allLiveSteps.value.slice(0, revealedCount.value)
)

// The most recently revealed step — shown in the collapsed header so the
// status line narrates what is happening, updating at the reveal cadence.
const latestLiveStep = computed(() => {
  const steps = thinkingSteps.value
  return steps.length ? steps[steps.length - 1].message : null
})

watch(
  () => thinkingSteps.value.length,
  async () => {
    await nextTick()
    if (thinkingPanelRef.value) {
      thinkingPanelRef.value.scrollTop = thinkingPanelRef.value.scrollHeight
    }
  }
)

watch(thinkingText, async () => {
  await nextTick()
  if (thinkingPanelRef.value) {
    thinkingPanelRef.value.scrollTop = thinkingPanelRef.value.scrollHeight
  }
})

function formatDuration(seconds) {
  if (seconds == null) return ''
  const s = Math.round(seconds)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

const elapsedText = computed(() => {
  if (elapsedSeconds.value === 0) return null
  return formatDuration(elapsedSeconds.value)
})

function thinkingStepsFor(events) {
  const grouped = []
  for (const e of events || []) {
    const msg = _liveStepLabel({
      agentEvent: e.agent_event,
      activity: e.activity,
      summary: e.summary
    })
    if (!msg) continue
    const last = grouped[grouped.length - 1]
    if (last && last.message === msg) {
      last.count++
    } else {
      grouped.push({ id: `${grouped.length}`, message: msg, count: 1 })
    }
  }
  return grouped
}

const expandedThinking = ref(new Set())

function toggleThinking(uuid) {
  const next = new Set(expandedThinking.value)
  if (next.has(uuid)) {
    next.delete(uuid)
  } else {
    next.add(uuid)
  }
  expandedThinking.value = next
}

const decoratedMessages = computed(() =>
  messages.value
    .filter(
      (m) => !(m.role === 'assistant' && !(m.content || '').trim())
    )
    .map((message) => {
      if (message.role === 'assistant' && message.thinking?.steps?.length) {
        const steps = thinkingStepsFor(message.thinking.steps)
        if (steps.length) {
          return { ...message, _thinkingSteps: steps }
        }
      }
      return message
    })
)

// A finished turn that produced no answer text — show a transient,
// retry-oriented hint (framed as a temporary hiccup, not a product fault)
// instead of an empty bubble.
const showRetryHint = computed(() => {
  if (isRunActive.value) return false
  const last = messages.value[messages.value.length - 1]
  return !!last && last.role === 'assistant' && !(last.content || '').trim()
})

watch(isRunActive, (active) => {
  if (active) {
    elapsedSeconds.value = 0
    elapsedTimer = setInterval(() => { elapsedSeconds.value++ }, 1000)
    revealTimer = setInterval(() => {
      if (revealedCount.value < allLiveSteps.value.length) {
        revealedCount.value++
      }
    }, REVEAL_INTERVAL_MS)
  } else {
    clearInterval(elapsedTimer)
    elapsedTimer = null
    clearInterval(revealTimer)
    revealTimer = null
    // flush any buffered steps once the run settles
    revealedCount.value = allLiveSteps.value.length
  }
})

const { isMobile } = useIsMobile()

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
  streamController.value?.abort()
  partialAnswer.value = ''
  streamError.value = ''
  streamEvents.value = []
  queuePosition.value = null
  thinkingPanelOpen.value = false
  thinkingText.value = ''
  elapsedSeconds.value = 0
  revealedCount.value = 0
  seenActivityKeys.clear()
  seenStepEventCounts.clear()
}

function pushAgentActivity(item, fallbackTs, fallbackStatus) {
  if (!item?.message && !item?.agent_event) {
    return
  }
  const key = `${item.agent_event || ''}|${item.summary || item.message || ''}`
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
    summary: item.summary || '',
    ts: fallbackTs || new Date().toISOString()
  })
}

function appendAnswerDelta(content) {
  partialAnswer.value += content
  nextTick(scrollToBottom)
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
  // Reset transient chat state up front so the previous assistant's draft,
  // active-run/stream state, or messages cannot leak across an assistant
  // switch (this runs on every slug change, before the async session load
  // below). selectedSessionUuid is intentionally NOT cleared here: if the
  // session load below throws, an empty uuid would leave the composer
  // permanently disabled. A stale submit during the brief load window is
  // instead guarded inside submit() by binding to the session it started in.
  question.value = ''
  currentRun.value = null
  messages.value = []
  resetStreamState()
  booted.value = false

  // Anonymous visitors can browse the shared chat page and see the
  // assistant name, but only authenticated users load private sessions.
  if (isAnonymous.value) {
    try {
      publicAssistant.value = await getPublicAssistant(route.params.slug)
    } catch {
      publicAssistant.value = null
      showError(t('lens.chat.loadFailed'))
    }
    booted.value = true
    return
  }

  try {
    assistants.value = await listAssistants()

    const current =
      assistants.value.find((item) => item.slug === route.params.slug) ||
      assistants.value[0]

    if (!current) {
      // No assistants exist yet — surface the create-first-assistant guide
      // (admin) or a no-assistant notice (end-user) instead of a spinner.
      booted.value = true
      return
    }

    if (current.slug !== route.params.slug) {
      // Re-bootstraps under the canonical slug; keep showing the loader.
      await router.replace(`/lens/assistants/${current.slug}/chat`)
      return
    }

    selectedAssistantUuid.value = current.uuid
    await loadSessions()
    booted.value = true
  } catch {
    showError(t('lens.chat.loadFailed'))
    booted.value = true
  }
}

function requireLogin() {
  showLoginModal.value = true
}

async function onLoginSuccess() {
  showLoginModal.value = false
  // Load the now-authenticated user's assistants and sessions so the
  // composer becomes usable without a full page reload.
  await bootstrap()
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
    await selectSession({ uuid: targetUuid })
  }
  await nextTick(() => composerRef.value?.focus())
}

async function createNewSession(notify = true) {
  if (!selectedAssistant.value) {
    return null
  }

  const session = await createSession({
    assistant_uuid: selectedAssistant.value.uuid,
    title: ''
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
    showSuccess(t('lens.chat.sessionCreated'))
  }

  return session
}

function setSessionTitle(uuid, title) {
  const session = sessions.value.find((item) => item.uuid === uuid)
  if (session) {
    session.title = title
  }
}

function deriveSessionTitle(text) {
  const clean = (text || '').replace(/\s+/g, ' ').trim()
  return clean.length > 24 ? `${clean.slice(0, 24)}…` : clean
}

function startRename(session) {
  deletingSessionUuid.value = ''
  renamingSessionUuid.value = session.uuid
  renameDraft.value = session.title || ''
  nextTick(() => {
    const el = document.querySelector('.session-rename-input')
    if (el) {
      el.focus()
      el.select()
    }
  })
}

function cancelRename() {
  renamingSessionUuid.value = ''
  renameDraft.value = ''
}

async function saveRename(session) {
  // Enter and blur can both fire; the guard makes the save idempotent.
  if (renamingSessionUuid.value !== session.uuid) {
    return
  }
  const title = renameDraft.value.trim()
  renamingSessionUuid.value = ''
  renameDraft.value = ''
  if (title === (session.title || '')) {
    return
  }
  const previous = session.title || ''
  setSessionTitle(session.uuid, title)
  try {
    await updateSession(session.uuid, { title })
  } catch {
    setSessionTitle(session.uuid, previous)
    showError(t('lens.chat.renameFailed'))
  }
}

function insertNewline() {
  const el = composerRef.value
  if (!el) return
  const start = el.selectionStart
  const end = el.selectionEnd
  question.value = question.value.slice(0, start) + '\n' + question.value.slice(end)
  nextTick(() => {
    el.selectionStart = el.selectionEnd = start + 1
    autoResizeTextarea(el)
  })
}

function autoResizeTextarea(el) {
  const target = el?.target ?? el
  if (!target) return
  target.style.height = 'auto'
  target.style.height = Math.min(target.scrollHeight, 200) + 'px'
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
  currentRun.value = null
  resetStreamState()
  if (updateRoute) {
    router.replace({
      path: route.path,
      query: { session: session.uuid }
    })
  }
  await nextTick(scrollToBottom)
  maybeResumeActiveRun(session.uuid)
}

// If the session has a run still in progress (e.g. the user navigated away
// mid-answer), re-attach the SSE stream so the live thinking panel and
// streamed answer resume, then finalize like a normal run.
async function maybeResumeActiveRun(sessionUuid) {
  // the latest message carrying a run uuid (the user message of the most
  // recent turn) tells us whether that turn is still in progress
  const withRun = [...messages.value].reverse().find((m) => m.run)
  if (!withRun) return
  let run
  try {
    run = await getRun(withRun.run)
  } catch {
    return
  }
  if (!['queued', 'running', 'streaming'].includes(run?.status)) return
  if (selectedSessionUuid.value !== sessionUuid) return
  // hand the trailing in-progress assistant placeholder to the live row to
  // avoid showing it twice; the SSE sync replays its content and steps
  const last = messages.value[messages.value.length - 1]
  if (last && last.role === 'assistant') {
    messages.value = messages.value.slice(0, -1)
  }
  currentRun.value = run
  try {
    await readSse(run.uuid)
    currentRun.value = await getRun(run.uuid)
  } catch {
    // stream aborted (e.g. the user switched sessions) — fall through
  }
  if (selectedSessionUuid.value !== sessionUuid) return
  messages.value = await listMessages(sessionUuid)
  resetStreamState()
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
    if (event.status !== 'queued') queuePosition.value = null
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
  if (event.type === 'queue_position') {
    queuePosition.value = event.position
  }
  if (event.type === 'sync' && event.content) {
    partialAnswer.value = event.content
  }
  if (event.type === 'step') {
    handleStepEvent(event, event.ts)
  }
  if (event.type === 'token_reset') {
    if (partialAnswer.value) {
      thinkingText.value += partialAnswer.value + '\n'
    }
    partialAnswer.value = ''
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
  // Unauthenticated visitors must log in before sending a message.
  if (isAnonymous.value) {
    requireLogin()
    return
  }
  // Bind this submit to the session it started in. If the user switches
  // assistant/session mid-flight, the stream is aborted on purpose — that is
  // not a failure, so we must not restore the draft, alarm the user, or write
  // into the now-current assistant's state.
  const sessionAtSubmit = selectedSessionUuid.value
  const isFirstMessage = messages.value.length === 0
  loading.value.run = true
  resetStreamState()
  const optimisticText = question.value.replace(/^\s*\n+|\n+\s*$/g, '')
  question.value = ''
  if (composerRef.value) composerRef.value.style.height = 'auto'
  messages.value = [...messages.value, { role: 'user', content: optimisticText, uuid: '__optimistic__', created_at: new Date().toISOString() }]
  await nextTick(scrollToBottom)

  // Name a brand-new conversation after its first question (skip if the
  // user already gave it a title). Optimistic + best-effort persistence.
  const sessionAtSubmitObj = sessions.value.find(
    (item) => item.uuid === sessionAtSubmit
  )
  if (isFirstMessage && optimisticText && !(sessionAtSubmitObj?.title || '').trim()) {
    const autoTitle = deriveSessionTitle(optimisticText)
    if (autoTitle) {
      setSessionTitle(sessionAtSubmit, autoTitle)
      updateSession(sessionAtSubmit, { title: autoTitle }).catch(() => {})
    }
  }
  try {
    const run = await createRun(sessionAtSubmit, {
      question: optimisticText,
      run_inline: false,
      enqueue: true
    })
    // switched away between createRun and here — don't bind this run's live
    // state onto the now-current assistant
    if (selectedSessionUuid.value !== sessionAtSubmit) return
    currentRun.value = run
    pushStreamEvent({
      label: t('lens.chat.events.submitted'),
      status: run.status,
      message: run.uuid,
      ts: new Date().toISOString()
    })
    await readSse(run.uuid)
    // switched away while streaming — leave the new assistant untouched
    if (selectedSessionUuid.value !== sessionAtSubmit) return
    currentRun.value = await getRun(run.uuid)
    messages.value = await listMessages(sessionAtSubmit)

    if (currentRun.value?.status === 'failed') {
      // Remove the empty pre-created assistant placeholder from the failed run
      const last = messages.value[messages.value.length - 1]
      if (last?.role === 'assistant' && !last.content) {
        messages.value = messages.value.slice(0, -1)
      }
      const errMsg = currentRun.value.error || t('lens.chat.events.error')
      streamError.value = errMsg
      showError(errMsg)
    } else {
      await nextTick()
      resetStreamState()
    }
    await nextTick(scrollToBottom)
  } catch (err) {
    // a deliberate stream abort (switch/navigate) or a switch away is not a
    // submit failure — bail silently without touching the current state
    if (err?.name === 'AbortError' || selectedSessionUuid.value !== sessionAtSubmit) {
      return
    }
    messages.value = messages.value.filter(m => m.uuid !== '__optimistic__')
    question.value = optimisticText
    showError(t('lens.chat.submitFailed'))
  } finally {
    if (selectedSessionUuid.value === sessionAtSubmit) {
      loading.value.run = false
    }
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
    showSuccess(t('lens.chat.messageCopied'))
  } catch {
    showWarning(t('lens.chat.copyFailed'))
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

async function doDeleteSession(session) {
  deletingSessionUuid.value = ''
  try {
    await deleteSession(session.uuid)
    sessions.value = sessions.value.filter((s) => s.uuid !== session.uuid)
    if (selectedSessionUuid.value === session.uuid) {
      const next = sessions.value[0]
      if (next) {
        await selectSession(next)
      } else {
        selectedSessionUuid.value = ''
        messages.value = []
      }
    }
    showSuccess(t('lens.chat.sessionDeleted'))
  } catch {
    showError(t('lens.chat.deleteFailed'))
  }
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
    dockMenuOpen.value = false
    // On a hard load with a stored token, defer the first bootstrap to
    // onMounted so it runs after the user is hydrated — avoids a flash of
    // the anonymous view and a redundant public fetch.
    if (!userStore.user && localStorage.getItem('access_token')) {
      return
    }
    bootstrap()
  },
  { immediate: true }
)

onMounted(async () => {
  document.addEventListener('click', handleOutsideClick)
  if (window.innerWidth < 1024) {
    sidebarOpen.value = false
  }
  // Public route: hydrate a stored user (if any), then bootstrap once.
  if (!userStore.user && localStorage.getItem('access_token')) {
    await userStore.checkAuthStatus()
    bootstrap()
  }
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleOutsideClick)
  streamController.value?.abort()
  clearInterval(elapsedTimer)
  clearInterval(revealTimer)
})
</script>

<style scoped>
.lens-chat-page {
  @apply flex h-screen w-full overflow-hidden;
  background: #ffffff;
  color: #111827;
}

.sidebar {
  @apply flex h-full flex-shrink-0 flex-col border-r transition-all duration-300 ease-in-out;
  background: #ffffff;
  border-color: #e5e7eb;
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
  color: #374151;
}

.sidebar-collapse-btn:hover {
  background: #f3f4f6;
}

.sidebar-collapse-btn svg {
  @apply h-5 w-5;
}

.new-chat-btn {
  @apply flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors;
  color: #374151;
}

.new-chat-btn:hover {
  background: #f3f4f6;
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
  color: #6b7280;
}

.sessions-list {
  @apply space-y-1;
}

.session-item {
  @apply flex w-full items-center gap-2 rounded-xl px-3 py-2 text-left transition-all duration-150;
}

.session-item:hover {
  background: #f3f4f6;
}

.session-item-active {
  background: #e5e7eb;
}

.session-item-deleting {
  background: #fff1f2;
}

.session-title {
  @apply truncate text-sm font-medium;
  color: #111827;
}

.session-delete-btn,
.session-action-btn {
  @apply flex h-6 w-6 shrink-0 items-center justify-center rounded-md transition-colors;
}

.session-delete-btn svg,
.session-action-btn svg {
  @apply h-3.5 w-3.5;
}

.session-delete-btn {
  @apply opacity-0;
  color: #9ca3af;
}

.session-item:hover .session-delete-btn {
  @apply opacity-100;
}

.session-delete-btn:hover {
  background: #fee2e2;
  color: #ef4444;
}

.session-rename-btn {
  @apply flex h-6 w-6 shrink-0 items-center justify-center rounded-md opacity-0 transition-colors;
  color: #9ca3af;
}

.session-rename-btn svg {
  @apply h-3.5 w-3.5;
}

.session-item:hover .session-rename-btn {
  @apply opacity-100;
}

.session-rename-btn:hover {
  background: #eef2ff;
  color: #4f46e5;
}

.session-rename-input {
  @apply w-full rounded-md border px-2 py-1 text-sm font-medium outline-none;
  border-color: #c7d2fe;
  color: #111827;
}

.session-action-confirm {
  background: #ef4444;
  color: #ffffff;
}

.session-action-confirm:hover {
  background: #dc2626;
}

.session-action-cancel {
  background: #f3f4f6;
  color: #6b7280;
}

.session-action-cancel:hover {
  background: #e5e7eb;
}

.main-shell {
  @apply relative flex min-w-0 flex-1 flex-col overflow-hidden;
  background: #ffffff;
}

.mobile-topbar {
  @apply flex flex-shrink-0 items-center gap-1 border-b px-2 py-1.5;
  border-color: #e5e7eb;
}

.mobile-topbar-title {
  @apply min-w-0 flex-1 truncate text-center text-sm font-semibold text-ink-900;
}

.chat-header {
  @apply flex flex-shrink-0 items-center gap-3 border-b px-5 py-3;
  border-color: #e5e7eb;
}

.chat-header-title {
  @apply min-w-0 truncate text-base font-semibold text-ink-900;
}

.retry-hint {
  @apply flex flex-wrap items-center gap-3 rounded-lg border px-3 py-2.5 text-sm;
  border-color: #fde68a;
  background: #fffbeb;
  color: #92400e;
}

.retry-hint-text {
  @apply min-w-0 flex-1;
}

.retry-hint-btn {
  @apply shrink-0 rounded-md px-3 py-1 text-sm font-medium text-white transition-colors;
  background: #d97706;
}

.retry-hint-btn:hover {
  background: #b45309;
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
  @apply flex-row-reverse;
}

.message-avatar {
  @apply flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[9px] text-xs font-semibold;
}

.message-avatar.user {
  color: #fff;
}

.message-avatar.assistant {
  background: #ffffff;
  border: 1px solid #e5e7eb;
}

.message-body {
  @apply min-w-0 flex-1;
}

.message-row-user .message-body {
  @apply w-fit max-w-[640px] flex-none text-right;
}

.message-card {
  @apply min-w-0;
}

.message-time {
  @apply mt-1 text-xs;
  color: #9ca3af;
}

.message-time.user {
  @apply text-right;
}


.message-markdown :deep(.markdown-content) {
  @apply max-w-none break-words;
  color: #374151;
}

.message-markdown :deep(.markdown-content h1),
.message-markdown :deep(.markdown-content h2),
.message-markdown :deep(.markdown-content h3),
.message-markdown :deep(.markdown-content h4) {
  color: #111827;
}

.message-markdown :deep(.markdown-content p) {
  @apply mb-3 text-[16px] leading-7;
  color: #374151;
}

.message-markdown :deep(.markdown-content ul),
.message-markdown :deep(.markdown-content ol) {
  @apply mb-3 pl-5;
}

.message-markdown :deep(.markdown-content li) {
  @apply mb-2 text-[16px] leading-7;
  color: #374151;
}

.message-markdown :deep(.markdown-content :not(pre) > code) {
  background: #eef4fe;
  color: #0e278c;
}

.message-text {
  @apply whitespace-pre-wrap break-words text-[16px] leading-7;
  color: #111827;
}

.message-actions {
  @apply mt-3 flex gap-1;
}

.icon-btn {
  @apply flex h-[30px] w-[30px] items-center justify-center rounded-md transition-colors;
  color: #9ca3af;
}

.icon-btn:hover {
  background: #f3f4f6;
  color: #374151;
}

.icon-btn svg {
  @apply h-4 w-4;
}

.live-card,
.activity-card,
.timeline-card {
  @apply mb-9 max-w-[900px] rounded-lg border bg-white px-4 py-3;
  border-color: #e5e7eb;
}

.card-head {
  @apply flex items-center justify-between gap-3;
}

.card-title,
.card-heading {
  @apply text-xs font-semibold uppercase tracking-wide;
  color: #6b7280;
}

.card-state,
.card-caption {
  @apply text-xs;
  color: #6b7280;
}

.live-progress-row {
  @apply mb-2;
}

.thinking-panel {
  @apply w-full rounded-lg overflow-hidden;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
}

.thinking-panel-done {
  @apply mb-2;
  background: #fafafa;
}

.thinking-panel-live {
  @apply mb-2;
}

.thinking-done-icon {
  @apply shrink-0;
  color: #9ca3af;
}

.thinking-panel-header {
  @apply flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left;
  background: transparent;
  border: none;
}

.thinking-panel-header:hover {
  background: #f3f4f6;
}

.thinking-panel-status {
  @apply flex min-w-0 flex-1 items-center gap-1 text-sm;
  color: #374151;
}

.thinking-panel-status-text {
  @apply min-w-0 truncate;
}

.thinking-step-count {
  @apply rounded-full px-1.5 py-0.5 text-xs;
  background: #e5e7eb;
  color: #6b7280;
}

.thinking-elapsed {
  @apply shrink-0 text-xs tabular-nums;
  color: #9ca3af;
}

.thinking-panel-chevron {
  @apply shrink-0;
  color: #9ca3af;
}

.thinking-panel-body {
  @apply max-h-36 overflow-y-auto px-3 pb-2 pt-1;
  border-top: 1px solid #e5e7eb;
  scroll-behavior: smooth;
}

.thinking-step-item {
  @apply flex items-start gap-1.5 py-0.5 text-xs;
  color: #6b7280;
}

.thinking-step-bullet {
  @apply shrink-0;
  color: #d1d5db;
  line-height: 1.5;
}

.thinking-step-text {
  @apply min-w-0 flex-1 break-words;
}

.thinking-step-repeat {
  @apply ml-1 shrink-0 text-xs;
  color: #9ca3af;
}

.thinking-reasoning {
  @apply whitespace-pre-wrap break-words text-xs leading-5 mt-1 pt-1;
  border-top: 1px dashed #e5e7eb;
  color: #9ca3af;
  font-style: italic;
}

.live-progress-dot {
  @apply h-1.5 w-1.5 shrink-0 rounded-full;
  background: #2b4ee6;
  animation: cursor-blink 1s steps(2, start) infinite;
}

.live-text {
  @apply whitespace-pre-wrap text-[16px] leading-7;
  color: #111827;
}

.live-thinking {
  @apply flex items-center gap-2 text-sm;
  color: #4b5563;
}

.typing-dots {
  @apply inline-flex items-center gap-1;
}

.typing-dots span {
  @apply h-1.5 w-1.5 rounded-full;
  background: #9ca3af;
  animation: typing-dot 1.2s ease-in-out infinite;
}

.typing-dots span:nth-child(2) {
  animation-delay: 0.15s;
}

.typing-dots span:nth-child(3) {
  animation-delay: 0.3s;
}

.live-markdown.is-streaming :deep(.markdown-content > *:last-child)::after {
  content: '';
  @apply ml-1 inline-block h-4 w-1 align-middle;
  background: #2b4ee6;
  animation: cursor-blink 1s steps(2, start) infinite;
}

.activity-list {
  @apply mt-3 space-y-2;
}

.activity-item {
  @apply flex items-start justify-between gap-3 rounded-md px-3 py-2;
  background: #f9fafb;
}

.activity-title {
  @apply text-sm font-medium;
  color: #111827;
}

.activity-detail {
  @apply mt-1 truncate text-xs;
  color: #6b7280;
}

.activity-time,
.timeline-time {
  @apply shrink-0 text-xs;
  color: #6b7280;
}

.timeline-toggle {
  @apply flex w-full items-center justify-between gap-3 text-left;
}

.timeline-list {
  @apply mt-3;
}

.timeline-list > * + * {
  border-top: 1px solid #f3f4f6;
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
  color: #4b5563;
}

.timeline-message {
  @apply mt-2 whitespace-pre-wrap text-xs leading-5;
  color: #374151;
}

.composer-wrap {
  @apply pointer-events-none absolute inset-x-0 bottom-0 z-20 px-6 pb-5;
  background: linear-gradient(
    to top,
    rgba(255, 255, 255, 0.98) 36%,
    rgba(255, 255, 255, 0.78) 72%,
    rgba(255, 255, 255, 0) 100%
  );
}

.composer-inner {
  @apply mx-auto w-full max-w-[900px];
}

.composer-shell {
  @apply pointer-events-auto;
}

.composer {
  @apply flex items-center gap-3 rounded-2xl border border-line bg-white px-4 py-3 shadow-soft;
}

.composer:focus-within {
  @apply border-primary-300;
  box-shadow: 0 0 0 3px rgba(43, 78, 230, 0.08);
}

.composer-input {
  @apply flex-1 border-0 bg-transparent py-2 px-0 text-[16px] leading-6 outline-none;
  color: #111827;
  min-height: 2.5rem;
  max-height: 200px;
  resize: none;
  overflow-y: auto;
  align-self: flex-end;
}

.composer-input::placeholder {
  color: #9ca3af;
}

.composer-action-btn {
  @apply flex h-10 w-10 shrink-0 items-center justify-center rounded-full transition-colors;
  background: #111111;
  color: #fff;
}

.composer-action-btn:hover:not(:disabled) {
  background: #1f2937;
}

.composer-action-btn-stop {
  background: #111111;
}

.composer-action-btn:disabled {
  background: #e5e7eb;
  cursor: not-allowed;
}

.composer-action-btn svg {
  @apply h-[17px] w-[17px];
}

.disclaimer {
  @apply mt-3 text-center text-xs;
  color: #9ca3af;
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

.anon-login-btn {
  @apply flex w-full items-center justify-center gap-2 rounded-xl border border-primary-200 bg-primary-50 px-3 py-2.5 text-sm font-medium text-primary-700 shadow-sm transition-colors;
}

.anon-login-btn:hover {
  @apply border-primary-300 bg-primary-100;
}

.anon-login-btn-collapsed {
  @apply gap-0 px-0;
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
    width: min(86vw, 320px);
    border-right: none;
    border-radius: 0 1rem 1rem 0;
    box-shadow: 0 8px 40px rgba(0, 0, 0, 0.18);
  }

  .sidebar-open {
    @apply translate-x-0;
  }

  .side-head {
    @apply px-4 pt-5 pb-3;
  }

  .side-scroll {
    @apply px-4;
  }

  .new-chat-btn {
    @apply py-3;
  }

  .new-chat-btn span {
    @apply text-[15px];
  }

  .sessions-list {
    @apply space-y-1.5;
  }

  .session-item {
    @apply py-3 rounded-2xl;
  }

  .session-title {
    @apply text-[15px];
  }

  .sidebar-footer {
    @apply p-4;
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
    box-shadow: inset 1px 0 0 #e5e7eb;
  }
}
</style>
