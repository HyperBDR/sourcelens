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
              sidebarCollapsedActive ? t('common.expand') : t('common.collapse')
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
          <div class="sessions-head">
            <h2>{{ t('lens.chat.sessions') }}</h2>
          </div>
          <div class="sessions-list">
            <div
              v-for="session in sessions"
              :key="session.uuid"
              class="session-item"
              :class="[
                deletingSessionUuid === session.uuid
                  ? 'session-item-deleting'
                  : selectedSessionUuid === session.uuid
                    ? 'session-item-active'
                    : ''
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
                  @click="
                    deletingSessionUuid !== session.uuid &&
                    selectSession(session)
                  "
                >
                  <div
                    class="session-title"
                    :class="
                      deletingSessionUuid === session.uuid ? 'opacity-40' : ''
                    "
                  >
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
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2.5"
                        aria-hidden="true"
                      >
                        <path
                          d="M20 6 9 17l-5-5"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />
                      </svg>
                    </button>
                    <button
                      type="button"
                      class="session-action-btn session-action-cancel"
                      :aria-label="t('common.cancel')"
                      @click.stop="deletingSessionUuid = ''"
                    >
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2.5"
                        aria-hidden="true"
                      >
                        <path
                          d="M18 6 6 18M6 6l12 12"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />
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
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="1.8"
                        aria-hidden="true"
                      >
                        <path
                          d="M12 20h9"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />
                        <path
                          d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />
                      </svg>
                    </button>
                    <button
                      type="button"
                      class="session-delete-btn"
                      :aria-label="t('lens.chat.deleteSession')"
                      @click.stop="deletingSessionUuid = session.uuid"
                    >
                      <svg
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="1.8"
                        aria-hidden="true"
                      >
                        <path
                          d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                        />
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
        <UserDock
          :collapsed="sidebarCollapsedActive"
          :is-mobile="isMobile"
          @require-login="requireLogin"
          @open-my-shares="openMyShares"
        />
      </div>
    </aside>

    <main class="main-shell">
      <div v-if="isMobile" class="mobile-topbar">
        <button
          v-if="mySharesOpen"
          type="button"
          class="sidebar-collapse-btn"
          :aria-label="t('common.back')"
          @click="mySharesOpen = false"
        >
          <ArrowLeft :size="20" :stroke-width="2.1" aria-hidden="true" />
        </button>
        <button
          v-else
          type="button"
          class="sidebar-collapse-btn"
          :aria-label="t('lens.chat.sessions')"
          @click="sidebarOpen = true"
        >
          <PanelLeftOpen :size="20" :stroke-width="2.1" aria-hidden="true" />
        </button>
        <div class="mobile-topbar-title">
          {{ mySharesOpen ? t('lens.qa.mineTitle') : assistantName }}
        </div>
        <button
          type="button"
          class="sidebar-collapse-btn"
          :aria-label="t('lens.chat.newSession')"
          @click="createNewSession"
        >
          <Plus :size="20" :stroke-width="2.1" aria-hidden="true" />
        </button>
      </div>
      <header
        v-if="!isMobile && (mySharesOpen || assistantName)"
        class="chat-header"
      >
        <template v-if="mySharesOpen">
          <button
            type="button"
            class="chat-header-back"
            :aria-label="t('common.back')"
            @click="mySharesOpen = false"
          >
            <ArrowLeft :size="18" :stroke-width="2.1" aria-hidden="true" />
          </button>
          <span class="chat-header-title">{{ t('lens.qa.mineTitle') }}</span>
        </template>
        <template v-else>
          <div class="chat-header-assistant">
            <AssistantSwitcher v-if="switchable" mode="header" />
            <div v-else class="chat-header-title">{{ assistantName }}</div>
            <p
              v-if="assistantDescription"
              class="chat-header-description"
              :class="{ 'pl-2': switchable }"
              :title="assistantDescription"
            >
              {{ assistantDescription }}
            </p>
          </div>
          <router-link
            v-if="assistantSlug"
            :to="`/lens/assistants/${assistantSlug}/qa`"
            class="chat-header-link ml-auto"
          >
            <MessagesSquare :size="15" :stroke-width="2" aria-hidden="true" />
            {{ t('lens.qa.publicListLink') }}
          </router-link>
        </template>
      </header>
      <MySharesPanel v-if="mySharesOpen" />
      <template v-else>
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
              :class="
                message.role === 'user'
                  ? 'message-row-user'
                  : 'message-row-assistant'
              "
            >
              <div
                class="message-avatar"
                :class="[
                  message.role,
                  message.role === 'user' ? avatarBgColor : ''
                ]"
              >
                <Smile
                  v-if="message.role === 'user'"
                  :size="17"
                  :stroke-width="2"
                />
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
                    <ChevronDown
                      v-else
                      :size="13"
                      class="thinking-panel-chevron"
                    />
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
                  <div
                    v-if="message.role === 'assistant' && message.content"
                    class="message-markdown"
                  >
                    <MarkdownRenderer :content="message.content" />
                  </div>
                  <template v-else>
                    <div
                      v-if="message.attachments && message.attachments.length"
                      class="message-images"
                    >
                      <AuthImage
                        v-for="img in message.attachments"
                        :key="img.uuid || img.localUrl"
                        :src="img.localUrl || img.url"
                        :alt="img.original_name || 'image'"
                        zoomable
                      />
                    </div>
                    <div v-if="message.content" class="message-text">
                      {{ message.content }}
                    </div>
                  </template>
                  <div
                    v-if="message.output_files && message.output_files.length"
                    class="message-deliverables"
                  >
                    <div
                      v-for="file in message.output_files"
                      :key="file.uuid"
                      class="deliverable-card"
                    >
                      <button
                        type="button"
                        class="deliverable-open"
                        @click="handleCardClick(file)"
                      >
                        <span class="deliverable-thumb">
                          <FileText :size="20" />
                        </span>
                        <span class="deliverable-meta">
                          <span class="deliverable-name">{{
                            file.filename
                          }}</span>
                          <span class="deliverable-sub">{{
                            fileTypeLabel(file)
                          }}</span>
                        </span>
                      </button>
                      <span class="deliverable-actions">
                        <button
                          v-if="isPreviewable(file)"
                          type="button"
                          class="deliverable-action"
                          :title="t('lens.chat.preview')"
                          @click="openPreview(file)"
                        >
                          <Eye :size="18" />
                        </button>
                        <button
                          type="button"
                          class="deliverable-action"
                          :title="t('lens.chat.download')"
                          @click="downloadOutputFile(file)"
                        >
                          <Download :size="18" />
                        </button>
                      </span>
                    </div>
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
                      <path
                        d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
                      />
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
                  <button
                    v-if="!isAnonymous && message.run"
                    type="button"
                    class="icon-btn"
                    :class="{ 'icon-btn-shared': isMessageShared(message) }"
                    :title="
                      isMessageShared(message)
                        ? t('lens.qa.sharedButton')
                        : t('lens.qa.shareButton')
                    "
                    @click="openShare(message)"
                  >
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      aria-hidden="true"
                    >
                      <circle cx="18" cy="5" r="3" />
                      <circle cx="6" cy="12" r="3" />
                      <circle cx="18" cy="19" r="3" />
                      <path
                        d="M8.59 13.51l6.83 3.98M15.41 6.51l-6.82 3.98"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </button>
                </div>
              </div>
            </div>

            <!-- Empty-answer hint: a finished turn returned no text -->
            <div v-if="showRetryHint" class="message-row message-row-assistant">
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
                    {{ retryHintMessage }}
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
                <div
                  v-if="isRunActive"
                  class="thinking-panel thinking-panel-live"
                >
                  <button
                    type="button"
                    class="thinking-panel-header"
                    @click="thinkingPanelOpen = !thinkingPanelOpen"
                  >
                    <span class="live-progress-dot" />
                    <span class="thinking-panel-status">
                      <span class="thinking-panel-status-text">{{
                        latestLiveStep ||
                        latestActivityMessage ||
                        liveStatusText
                      }}</span>
                      <span
                        v-if="!latestLiveStep && !latestActivityMessage"
                        class="typing-dots"
                        aria-hidden="true"
                      >
                        <span /><span /><span />
                      </span>
                    </span>
                    <span v-if="elapsedText" class="thinking-elapsed">{{
                      elapsedText
                    }}</span>
                    <span
                      v-if="thinkingSteps.length > 0"
                      class="thinking-step-count"
                    >
                      {{ thinkingSteps.length }}
                    </span>
                    <ChevronUp
                      v-if="
                        thinkingPanelOpen &&
                        (thinkingSteps.length > 0 || thinkingText)
                      "
                      :size="13"
                      class="thinking-panel-chevron"
                    />
                    <ChevronDown
                      v-else-if="thinkingSteps.length > 0 || thinkingText"
                      :size="13"
                      class="thinking-panel-chevron"
                    />
                  </button>
                  <div
                    v-if="
                      thinkingPanelOpen &&
                      (thinkingSteps.length > 0 || thinkingText)
                    "
                    ref="thinkingPanelRef"
                    class="thinking-panel-body"
                  >
                    <div
                      v-for="step in thinkingSteps"
                      :key="step.id"
                      class="thinking-step-item"
                    >
                      <span class="thinking-step-bullet">▸</span>
                      <span class="thinking-step-text">{{ step.message }}</span>
                      <span v-if="step.count > 1" class="thinking-step-repeat"
                        >×{{ step.count }}</span
                      >
                    </div>
                    <div v-if="thinkingText" class="thinking-reasoning">
                      {{ thinkingText }}
                    </div>
                  </div>
                </div>

                <div
                  v-if="partialAnswer || streamError"
                  class="message-card assistant"
                >
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
              <div v-if="attachments.length" class="composer-attachments">
                <div
                  v-for="item in attachments"
                  :key="item.key"
                  class="composer-thumb"
                  :class="{ 'is-uploading': item.status === 'uploading' }"
                >
                  <img :src="item.localUrl" :alt="item.name" />
                  <span
                    v-if="item.status === 'uploading'"
                    class="composer-thumb-spinner"
                  />
                  <button
                    type="button"
                    class="composer-thumb-remove"
                    :aria-label="t('lens.chat.removeImage')"
                    @click="removeAttachment(item)"
                  >
                    ×
                  </button>
                </div>
              </div>
              <div class="composer">
                <input
                  ref="fileInput"
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  multiple
                  class="composer-file-input"
                  @change="onFileInputChange"
                />
                <button
                  v-if="acceptsImages"
                  class="composer-attach-btn"
                  type="button"
                  :disabled="
                    !selectedSessionUuid || attachments.length >= MAX_IMAGES
                  "
                  :aria-label="t('lens.chat.attachImage')"
                  :title="t('lens.chat.attachImage')"
                  @click="triggerFilePick"
                >
                  <svg
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.2"
                    aria-hidden="true"
                  >
                    <path d="M12 5v14M5 12h14" stroke-linecap="round" />
                  </svg>
                </button>
                <textarea
                  ref="composerRef"
                  v-model="question"
                  class="composer-input"
                  rows="1"
                  :placeholder="t('lens.chat.questionPlaceholder')"
                  @keydown.enter.exact.prevent="insertNewline"
                  @keydown.ctrl.enter.exact.prevent="handlePrimaryAction"
                  @paste="onComposerPaste"
                  @input="autoResizeTextarea"
                />
                <button
                  class="composer-action-btn"
                  :class="isRunActive ? 'composer-action-btn-stop' : ''"
                  type="button"
                  :disabled="
                    (!isAnonymous && !selectedSessionUuid) ||
                    (!canSubmit && !isRunActive)
                  "
                  :aria-label="
                    isRunActive ? t('common.stop') : t('common.submit')
                  "
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
              {{
                t('lens.chat.disclaimer') ||
                '回答由 AI 生成，请自行核实关键信息。'
              }}
            </p>
          </div>
        </div>
      </template>
    </main>

    <LoginModal
      :show="showLoginModal"
      @close="showLoginModal = false"
      @success="onLoginSuccess"
    />

    <QaShareModal
      :open="shareOpen"
      :run-uuid="shareRunUuid"
      :existing-share="shareExisting"
      :question="shareQuestion"
      :answer-preview="shareAnswer"
      @close="shareOpen = false"
      @shared="handleShareUpdated"
      @unshared="handleShareRemoved"
    />

    <FilePreviewModal
      :file="previewFile"
      @close="closePreview"
      @download="downloadOutputFile"
    />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch, nextTick } from 'vue'
import {
  ArrowLeft,
  MessagesSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Smile,
  ChevronDown,
  ChevronUp,
  Download,
  Eye,
  FileText,
  Sparkles
} from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import MarkdownRenderer from '@/components/ui/MarkdownRenderer.vue'
import AuthImage from '@/components/ui/AuthImage.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import BrandLogo from '@/components/layout/BrandLogo.vue'
import AssistantSwitcher from '@/components/lens/AssistantSwitcher.vue'
import UserDock from '@/components/lens/UserDock.vue'
import MySharesPanel from '@/components/lens/MySharesPanel.vue'
import AssistantEmptyState from '@/components/lens/AssistantEmptyState.vue'
import LoginModal from '@/components/auth/LoginModal.vue'
import QaShareModal from '@/components/lens/QaShareModal.vue'
import FilePreviewModal from '@/components/lens/FilePreviewModal.vue'
import {
  extensionOf,
  fetchDeliverableBlob,
  isPreviewable
} from '@/utils/filePreview'
import { useToast } from '@/composables/useToast'
import { useIsMobile } from '@/composables/useIsMobile'
import apiConfig from '@/config/api'
import { useLensStore } from '@/store/lens'
import { useUserStore } from '@/store/user'
import {
  cancelRun,
  createRun,
  createSession,
  deleteSession,
  getPublicAssistant,
  getRun,
  listMyShares,
  listAssistants,
  listMessages,
  listSessions,
  updateSession,
  uploadAttachment
} from '@/api/lens'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { showError, showSuccess, showWarning } = useToast()
const userStore = useUserStore()
const lensStore = useLensStore()

const assistants = ref([])
const sessions = ref([])
const messages = ref([])
const selectedAssistantUuid = ref('')
const selectedSessionUuid = ref('')
const question = ref('')
const attachments = ref([])
const fileInput = ref(null)
const partialAnswer = ref('')

const MAX_IMAGES = 4
const MAX_IMAGE_BYTES = 10 * 1024 * 1024
const IMAGE_MIME = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
const RUN_POLL_INTERVAL_MS = 3000
const RUN_POLL_MAX_ATTEMPTS = 160
const streamError = ref('')
const failedRunError = ref(null)
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
const composerRef = ref(null)
const scrollRef = ref(null)
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
const shareOpen = ref(false)
const shareRunUuid = ref('')
const shareAnswer = ref('')
const shareQuestion = ref('')
const shareExisting = ref(null)
const sharesByRun = ref({})
const mySharesOpen = ref(false)
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

// Image upload requires both a multimodal-capable assistant and login (the
// upload endpoint is authenticated), so anonymous visitors never see it.
const acceptsImages = computed(
  () => !isAnonymous.value && !!selectedAssistant.value?.multimodal_model_ref
)

const hasUploadingImage = computed(() =>
  attachments.value.some((item) => item.status === 'uploading')
)

const canSubmit = computed(() => {
  if (hasUploadingImage.value) {
    return false
  }
  const hasReadyImage = attachments.value.some((item) => item.status === 'done')
  return !!question.value.trim() || hasReadyImage
})

const hasAssistant = computed(() =>
  isAnonymous.value ? !!publicAssistant.value : !!selectedAssistantUuid.value
)

const emptyVariant = computed(() =>
  userStore.userHasFeature('admin_console') ? 'admin' : 'visitor'
)

const assistantName = computed(
  () => selectedAssistant.value?.name || publicAssistant.value?.name || ''
)

const assistantDescription = computed(
  () =>
    selectedAssistant.value?.description?.trim() ||
    publicAssistant.value?.description?.trim() ||
    ''
)

// The top header turns the assistant name into a switcher only when an
// authenticated user has more than one assistant to choose from. Mirror the
// switcher's own visibility rule (active assistants only) so the header never
// renders an empty switcher in place of the name.
const switchable = computed(
  () =>
    !isAnonymous.value &&
    assistants.value.filter((item) => item.status === 'active').length > 1
)

// Slug of the assistant in view — drives the public Q&A list entry in the
// header for both authenticated and anonymous visitors.
const assistantSlug = computed(() => route.params.slug || '')

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
    task: t('lens.chat.activity.delegatingTask')
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
  if (activity === 'loading_resources')
    return t('lens.chat.activity.loadingResources')
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
      (m) =>
        !(
          m.role === 'assistant' &&
          !(m.content || '').trim() &&
          !m.thinking?.steps?.length
        )
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

// Map a backend run error code to a clear, blame-clarifying message: a
// timeout is the model being slow (after retries), not a platform fault.
function mapRunError(code) {
  const c = String(code || '').toUpperCase()
  if (c.includes('TIMEOUT')) {
    return t('lens.chat.errorModelTimeout')
  }
  if (c.includes('DISCONNECT') || c.includes('ORPHAN')) {
    return t('lens.chat.errorNodeLost')
  }
  return t('lens.chat.emptyAnswerHint')
}

function isTerminalRunStatus(status) {
  return ['done', 'failed', 'cancelled'].includes(status)
}

const retryHintMessage = computed(() =>
  failedRunError.value
    ? mapRunError(failedRunError.value)
    : t('lens.chat.emptyAnswerHint')
)

watch(isRunActive, (active) => {
  if (active) {
    elapsedSeconds.value = 0
    elapsedTimer = setInterval(() => {
      elapsedSeconds.value++
    }, 1000)
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
  failedRunError.value = null
  streamEvents.value = []
  queuePosition.value = null
  thinkingPanelOpen.value = false
  thinkingText.value = ''
  elapsedSeconds.value = 0
  revealedCount.value = 0
  seenActivityKeys.clear()
  seenStepEventCounts.clear()
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function waitForRunTerminal(runUuid) {
  let run = await getRun(runUuid)
  for (let attempt = 0; attempt < RUN_POLL_MAX_ATTEMPTS; attempt += 1) {
    if (isTerminalRunStatus(run?.status)) {
      return run
    }
    await sleep(RUN_POLL_INTERVAL_MS)
    run = await getRun(runUuid)
  }
  return run
}

async function finishSubmittedRun(runUuid, sessionUuid) {
  currentRun.value = await getRun(runUuid)
  messages.value = await listMessages(sessionUuid)

  if (currentRun.value?.status === 'failed') {
    const errorCode = currentRun.value.error || 'RUN_FAILED'
    resetStreamState()
    failedRunError.value = errorCode
    showError(mapRunError(errorCode))
  } else {
    await nextTick()
    resetStreamState()
  }
  await nextTick(scrollToBottom)
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
  mySharesOpen.value = false
  resetStreamState()
  booted.value = false

  // Anonymous visitors can browse the shared chat page and see the
  // assistant name, but only authenticated users load private sessions.
  if (isAnonymous.value) {
    try {
      publicAssistant.value = await getPublicAssistant(route.params.slug)
    } catch {
      publicAssistant.value = null
      showError(t('lens.chat.assistantNotFound'))
    }
    booted.value = true
    return
  }

  try {
    assistants.value = await listAssistants()
    // Share the loaded list with the store so the header AssistantSwitcher
    // renders immediately (no flash) and skips its own redundant fetch.
    lensStore.assistants = assistants.value

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
    await loadMyShareState()
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

function openMyShares() {
  mySharesOpen.value = true
  if (isMobile.value) {
    sidebarOpen.value = false
  }
}

async function onLoginSuccess() {
  showLoginModal.value = false
  // Load the now-authenticated user's assistants and sessions so the
  // composer becomes usable without a full page reload.
  await bootstrap()
}

async function loadMyShareState() {
  try {
    const shares = await listMyShares()
    sharesByRun.value = Object.fromEntries(
      shares
        .filter((share) => share.run_uuid)
        .map((share) => [share.run_uuid, share])
    )
  } catch {
    sharesByRun.value = {}
  }
}

async function loadSessions(selectUuid = '') {
  if (!selectedAssistant.value) {
    return
  }

  sessions.value = await listSessions(selectedAssistant.value.slug)

  const requestedUuid = selectUuid || route.query.session || ''
  let targetUuid = requestedUuid || sessions.value[0]?.uuid
  if (
    requestedUuid &&
    !sessions.value.some((session) => session.uuid === requestedUuid)
  ) {
    showError(t('lens.chat.sessionAccessDenied'))
    targetUuid = sessions.value[0]?.uuid
    if (targetUuid) {
      router.replace({
        path: route.path,
        query: { session: targetUuid }
      })
    }
  }
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
  mySharesOpen.value = false

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

function triggerFilePick() {
  fileInput.value?.click()
}

async function onFileInputChange(event) {
  const files = Array.from(event.target.files || [])
  event.target.value = ''
  for (const file of files) {
    await addImage(file)
  }
}

async function onComposerPaste(event) {
  if (!acceptsImages.value) return
  const items = Array.from(event.clipboardData?.items || [])
  const images = items.filter(
    (item) => item.kind === 'file' && item.type.startsWith('image/')
  )
  if (!images.length) return
  // Only swallow the paste when it actually carries an image, so pasting
  // text into the composer keeps working normally.
  event.preventDefault()
  for (const item of images) {
    const file = item.getAsFile()
    if (file) await addImage(file)
  }
}

async function addImage(file) {
  if (!acceptsImages.value) return
  if (!IMAGE_MIME.includes(file.type)) {
    showError(t('lens.chat.imageUnsupported'))
    return
  }
  if (file.size > MAX_IMAGE_BYTES) {
    showError(t('lens.chat.imageTooLarge'))
    return
  }
  if (attachments.value.length >= MAX_IMAGES) {
    showError(t('lens.chat.imageTooMany', { max: MAX_IMAGES }))
    return
  }
  const sessionUuid = selectedSessionUuid.value
  if (!sessionUuid) return
  const item = {
    key: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
    uuid: '',
    name: file.name || 'image',
    localUrl: URL.createObjectURL(file),
    status: 'uploading'
  }
  attachments.value = [...attachments.value, item]
  try {
    const result = await uploadAttachment(sessionUuid, file)
    if (selectedSessionUuid.value !== sessionUuid) {
      removeAttachment(item)
      return
    }
    item.uuid = result.uuid
    item.status = 'done'
    attachments.value = [...attachments.value]
  } catch {
    removeAttachment(item)
    showError(t('lens.chat.imageUploadFailed'))
  }
}

function removeAttachment(item) {
  if (item.localUrl) URL.revokeObjectURL(item.localUrl)
  attachments.value = attachments.value.filter((entry) => entry !== item)
}

function clearAttachments() {
  attachments.value.forEach(
    (item) => item.localUrl && URL.revokeObjectURL(item.localUrl)
  )
  attachments.value = []
}

function insertNewline() {
  const el = composerRef.value
  if (!el) return
  const start = el.selectionStart
  const end = el.selectionEnd
  question.value =
    question.value.slice(0, start) + '\n' + question.value.slice(end)
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
  mySharesOpen.value = false
  clearAttachments()
  selectedSessionUuid.value = session.uuid
  try {
    messages.value = await listMessages(session.uuid)
  } catch (error) {
    if ([403, 404].includes(error?.response?.status)) {
      showError(t('lens.chat.sessionAccessDenied'))
      return
    }
    throw error
  }
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
  if (!['queued', 'running', 'streaming'].includes(run?.status)) {
    // A historically-failed turn keeps its retry hint with the right
    // (blame-clarifying) message after a reload, not just live.
    if (run?.status === 'failed') {
      failedRunError.value = run.error || 'RUN_FAILED'
    }
    return
  }
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
      const dataLine = raw.split('\n').find((line) => line.startsWith('data: '))
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
    streamError.value = event.error?.code
      ? mapRunError(event.error.code)
      : event.error?.message || event.error || t('lens.chat.events.error')
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

  const timelineItems = newEvents.length ? newEvents : [{ message: event.step }]
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
  if (!canSubmit.value) {
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
  // Snapshot ready images, clear the composer strip, and keep the object
  // URLs alive for the optimistic bubble until the server reload replaces it.
  const pendingImages = attachments.value.filter(
    (item) => item.status === 'done'
  )
  const attachmentUuids = pendingImages.map((item) => item.uuid)
  attachments.value = []
  // Revoke the optimistic object URLs on every exit path, unless they are
  // restored to the composer for a retry (set below on real failures).
  let keepImages = false
  if (composerRef.value) composerRef.value.style.height = 'auto'
  messages.value = [
    ...messages.value,
    {
      role: 'user',
      content: optimisticText,
      uuid: '__optimistic__',
      created_at: new Date().toISOString(),
      attachments: pendingImages.map((item) => ({
        localUrl: item.localUrl,
        original_name: item.name
      }))
    }
  ]
  await nextTick(scrollToBottom)

  // Name a brand-new conversation after its first question (skip if the
  // user already gave it a title). Optimistic + best-effort persistence.
  const sessionAtSubmitObj = sessions.value.find(
    (item) => item.uuid === sessionAtSubmit
  )
  if (
    isFirstMessage &&
    optimisticText &&
    !(sessionAtSubmitObj?.title || '').trim()
  ) {
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
      enqueue: true,
      attachment_uuids: attachmentUuids
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
    await finishSubmittedRun(run.uuid, sessionAtSubmit)
  } catch (err) {
    // a deliberate stream abort (switch/navigate) or a switch away is not a
    // submit failure — bail silently without touching the current state
    if (
      err?.name === 'AbortError' ||
      selectedSessionUuid.value !== sessionAtSubmit
    ) {
      return
    }
    const runUuid = currentRun.value?.uuid
    if (runUuid) {
      try {
        pushStreamEvent({
          label: t('lens.chat.events.error'),
          status: currentRun.value?.status || 'running',
          message: t('lens.chat.waitingForResult'),
          ts: new Date().toISOString()
        })
        const run = await waitForRunTerminal(runUuid)
        if (selectedSessionUuid.value !== sessionAtSubmit) return
        currentRun.value = run
        await finishSubmittedRun(runUuid, sessionAtSubmit)
        return
      } catch {
        // Fall through to the true submit-failure recovery path.
      }
    }
    messages.value = messages.value.filter((m) => m.uuid !== '__optimistic__')
    question.value = optimisticText
    // Restore the uploaded (still-unbound) images so the user can retry;
    // keep their object URLs alive for the composer thumbnails.
    if (pendingImages.length) {
      attachments.value = [...attachments.value, ...pendingImages]
      keepImages = true
    }
    showError(t('lens.chat.submitFailed'))
  } finally {
    if (!keepImages) {
      pendingImages.forEach(
        (item) => item.localUrl && URL.revokeObjectURL(item.localUrl)
      )
    }
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

const previewFile = ref(null)

function openPreview(file) {
  previewFile.value = file
}

function closePreview() {
  previewFile.value = null
}

function handleCardClick(file) {
  if (isPreviewable(file)) {
    openPreview(file)
  } else {
    downloadOutputFile(file)
  }
}

async function downloadOutputFile(file) {
  if (!file?.url) {
    return
  }
  try {
    const blob = await fetchDeliverableBlob(file)
    const objectUrl = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = objectUrl
    link.download = file.filename || 'download'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(objectUrl)
  } catch {
    showWarning(t('lens.chat.downloadFailed'))
  }
}

function formatBytes(size) {
  if (!size) {
    return ''
  }
  if (size < 1024) {
    return `${size} B`
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function fileTypeLabel(file) {
  const ext = extensionOf(file.filename).toUpperCase()
  const size = formatBytes(file.byte_size)
  return [ext, size].filter(Boolean).join(' · ')
}

function openShare(message) {
  shareRunUuid.value = message.run || ''
  shareExisting.value = sharesByRun.value[shareRunUuid.value] || null
  shareAnswer.value = message.content || ''
  shareQuestion.value = questionForMessage(message)
  shareOpen.value = true
}

function isMessageShared(message) {
  return Boolean(message.run && sharesByRun.value[message.run])
}

function handleShareUpdated(share) {
  if (!share?.run_uuid) {
    return
  }
  sharesByRun.value = {
    ...sharesByRun.value,
    [share.run_uuid]: share
  }
  shareExisting.value = share
}

function handleShareRemoved(share) {
  if (!share?.run_uuid) {
    return
  }
  const next = { ...sharesByRun.value }
  delete next[share.run_uuid]
  sharesByRun.value = next
  shareExisting.value = null
}

function questionForMessage(message) {
  const list = messages.value
  const idx = list.findIndex((item) => item.uuid === message.uuid)
  for (let i = idx - 1; i >= 0; i -= 1) {
    if (list[i].role === 'user') {
      return list[i].content || ''
    }
  }
  return ''
}

function retryLastQuestion() {
  const lastUserMessage = [...messages.value]
    .reverse()
    .find((message) => message.role === 'user')
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

watch(
  () => route.params.slug,
  () => {
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

.chat-header-assistant {
  @apply min-w-0 flex-1;
}

.chat-header-description {
  @apply mt-0.5 max-w-2xl truncate text-xs leading-5 text-ink-500;
}

.chat-header-back {
  @apply flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-ink-500 transition-colors;
}

.chat-header-back:hover {
  background: #f3f4f6;
  color: #374151;
}

.chat-header-link {
  @apply inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium no-underline transition-colors;
  border-color: #e5e7eb;
  color: #4b5563;
}

.chat-header-link:hover {
  background: #f9fafb;
  border-color: #d1d5db;
  color: #111827;
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
  @apply w-fit flex-none text-right;
  max-width: min(640px, calc(100% - 46px));
}

.message-card {
  @apply min-w-0;
}

.message-card.user {
  @apply rounded-2xl px-4 py-3 text-left;
  background: #f3f4f6;
  overflow-wrap: anywhere;
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

.icon-btn-shared {
  background: rgba(34, 197, 94, 0.1);
  color: #15803d;
}

.icon-btn-shared:hover {
  background: rgba(34, 197, 94, 0.16);
  color: #166534;
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

.composer-file-input {
  display: none;
}

.composer-attach-btn {
  @apply flex h-9 w-9 shrink-0 items-center justify-center rounded-full
    border border-line bg-white text-gray-500 transition-colors;
}

.composer-attach-btn:hover:not(:disabled) {
  @apply border-primary-300 text-primary-600;
}

.composer-attach-btn:disabled {
  @apply text-gray-300 cursor-not-allowed;
}

.composer-attach-btn svg {
  @apply h-[18px] w-[18px];
}

.composer-attachments {
  @apply mb-2 flex flex-wrap gap-2;
}

.composer-thumb {
  @apply relative h-16 w-16 overflow-hidden rounded-lg border border-line;
}

.composer-thumb img {
  @apply h-full w-full object-cover;
}

.composer-thumb.is-uploading img {
  opacity: 0.5;
}

.composer-thumb-spinner {
  @apply absolute left-1/2 top-1/2 h-5 w-5 -translate-x-1/2 -translate-y-1/2
    rounded-full border-2 border-gray-300 border-t-primary-500;
  animation: spin 0.7s linear infinite;
}

.composer-thumb-remove {
  @apply absolute right-0.5 top-0.5 flex h-5 w-5 items-center justify-center
    rounded-full bg-black/55 text-sm leading-none text-white;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.message-images {
  @apply mb-2 flex flex-wrap justify-end gap-2;
}

.message-images :deep(.auth-image) {
  max-width: 220px;
  max-height: 220px;
  object-fit: cover;
}

.message-deliverables {
  @apply mt-3 flex flex-col gap-2;
}

.deliverable-card {
  @apply flex w-full max-w-sm items-center gap-3 rounded-xl border
    border-line bg-white px-3 py-2.5 text-left transition-all;
}

.deliverable-card:hover {
  @apply border-primary-300 shadow-soft;
}

.deliverable-open {
  @apply flex min-w-0 flex-1 items-center gap-3 text-left;
}

.deliverable-thumb {
  @apply flex h-10 w-10 shrink-0 items-center justify-center rounded-lg
    bg-primary-50 text-primary-600;
}

.deliverable-meta {
  @apply flex min-w-0 flex-1 flex-col;
}

.deliverable-name {
  @apply truncate text-sm font-medium text-gray-800;
}

.deliverable-sub {
  @apply mt-0.5 text-xs uppercase tracking-wide text-gray-400;
}

.deliverable-actions {
  @apply flex shrink-0 items-center gap-1;
}

.deliverable-action {
  @apply flex h-8 w-8 shrink-0 items-center justify-center rounded-lg
    text-gray-400 transition-colors;
}

.deliverable-action:hover {
  @apply bg-primary-50 text-primary-600;
}

.disclaimer {
  @apply mt-3 text-center text-xs;
  color: #9ca3af;
}

.sidebar-footer {
  @apply border-t border-line p-3;
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
