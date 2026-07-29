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
                  <span
                    v-if="sessionHasUnreadAnswer(session.uuid)"
                    class="session-unread-indicator"
                    :title="t('lens.chat.unreadAnswer')"
                  >
                    <Bell :size="14" :stroke-width="2.2" aria-hidden="true" />
                    <span class="sr-only">
                      {{ t('lens.chat.unreadAnswer') }}
                    </span>
                  </span>
                  <template v-if="deletingSessionUuid === session.uuid">
                    <button
                      type="button"
                      class="session-action-btn session-action-confirm"
                      :aria-label="t('lens.chat.confirmDelete')"
                      :title="t('lens.chat.confirmDelete')"
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
                      :title="t('common.cancel')"
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
                      :title="t('lens.chat.renameSession')"
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
                      :title="t('lens.chat.deleteSession')"
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
                <span v-if="message.role === 'user'" aria-hidden="true">
                  {{ userInitials }}
                </span>
                <img
                  v-else
                  src="/brand/logo_transparent.png"
                  alt="SourceLens"
                  class="h-[20px] w-[20px] object-contain"
                />
              </div>

              <div class="message-body">
                <details
                  v-if="structuredProgress(message._runtimeState).items.length"
                  class="runtime-progress-card"
                >
                  <summary class="runtime-progress-summary">
                    <span class="runtime-card-title">
                      {{
                        progressTitle(
                          structuredProgress(message._runtimeState).kind,
                          structuredProgress(message._runtimeState).hasPlan
                        )
                      }}
                    </span>
                    <span class="runtime-progress-summary-text">
                      {{
                        structuredProgressText(
                          message._runtimeState,
                          message.thinking.duration_seconds,
                          true
                        )
                      }}
                    </span>
                    <span class="runtime-progress-chevron" aria-hidden="true">
                      ⌄
                    </span>
                  </summary>
                  <div
                    v-if="
                      structuredProgress(message._runtimeState).kind ===
                      'workflow'
                    "
                    class="runtime-workflow"
                  >
                    <div
                      v-for="task in structuredProgress(message._runtimeState)
                        .tasks"
                      :key="task.id"
                      class="runtime-workflow-task"
                      :class="{
                        'is-direct': !structuredProgress(message._runtimeState)
                          .hasPlan
                      }"
                    >
                      <div
                        v-if="structuredProgress(message._runtimeState).hasPlan"
                        class="runtime-plan-step runtime-task-row"
                        :class="{
                          'is-active-ancestor': isActiveProgressAncestor(
                            task,
                            task.stages
                          )
                        }"
                      >
                        <span
                          class="runtime-plan-status"
                          :class="[
                            `is-${task.status}`,
                            {
                              'is-active-ancestor': isActiveProgressAncestor(
                                task,
                                task.stages
                              )
                            }
                          ]"
                          aria-hidden="true"
                        >
                          {{ progressStatusIcon(task.status) }}
                        </span>
                        <span>{{ workflowTaskTitle(task) }}</span>
                      </div>
                      <div
                        v-for="stage in task.stages"
                        :key="stage.id"
                        class="runtime-workflow-stage"
                      >
                        <div
                          class="runtime-plan-step runtime-stage-row"
                          :class="{
                            'is-active-ancestor': isActiveProgressAncestor(
                              stage,
                              stage.steps
                            )
                          }"
                        >
                          <span
                            class="runtime-plan-status"
                            :class="[
                              `is-${stage.status}`,
                              {
                                'is-active-ancestor': isActiveProgressAncestor(
                                  stage,
                                  stage.steps
                                )
                              }
                            ]"
                            aria-hidden="true"
                          >
                            {{ progressStatusIcon(stage.status) }}
                          </span>
                          <span>{{ workflowStageTitle(stage.kind) }}</span>
                        </div>
                        <div class="runtime-workflow-steps">
                          <div
                            v-for="step in stage.steps"
                            :key="step.id"
                            class="runtime-plan-step runtime-step-row"
                          >
                            <span
                              class="runtime-plan-status"
                              :class="`is-${step.status}`"
                              aria-hidden="true"
                            >
                              {{ progressStatusIcon(step.status) }}
                            </span>
                            <span>{{ workflowStepTitle(step) }}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div
                    v-else-if="
                      structuredProgress(message._runtimeState).kind ===
                      'activity'
                    "
                    class="runtime-node-activities runtime-standalone-activities"
                  >
                    <div
                      v-for="activity in structuredProgress(
                        message._runtimeState
                      ).items"
                      :key="activity.id"
                      class="runtime-node-activity"
                    >
                      <span class="runtime-activity-indicator">✓</span>
                      <span>{{ activityLabel(activity.kind) }}</span>
                      <span
                        v-if="activity.count > 1"
                        class="runtime-activity-count"
                      >
                        ×{{ activity.count }}
                      </span>
                    </div>
                  </div>
                  <div
                    v-else
                    v-for="item in structuredProgress(message._runtimeState)
                      .items"
                    :key="item.id"
                    class="runtime-plan-node"
                  >
                    <div class="runtime-plan-step">
                      <span
                        class="runtime-plan-status"
                        :class="`is-${item.status}`"
                        aria-hidden="true"
                      >
                        {{ progressStatusIcon(item.status) }}
                      </span>
                      <span class="runtime-step-content">
                        <span>{{ item.title }}</span>
                        <span v-if="item.summary" class="runtime-step-summary">
                          {{ item.summary }}
                        </span>
                      </span>
                    </div>
                    <div
                      v-if="
                        nodeActivities(message._runtimeState, item.id).length
                      "
                      class="runtime-node-activities"
                    >
                      <div
                        v-for="activity in nodeActivities(
                          message._runtimeState,
                          item.id
                        )"
                        :key="activity.id"
                        class="runtime-node-activity"
                      >
                        <span class="runtime-activity-indicator">✓</span>
                        <span>{{ activityLabel(activity.kind) }}</span>
                        <span
                          v-if="activity.count > 1"
                          class="runtime-activity-count"
                        >
                          ×{{ activity.count }}
                        </span>
                      </div>
                    </div>
                  </div>
                </details>

                <div
                  v-if="message._runtimeState?.capabilityBlock"
                  class="runtime-block-card"
                  role="status"
                >
                  <div class="runtime-card-title">
                    {{ t('lens.chat.runtime.blockedTitle') }}
                  </div>
                  <div>
                    {{
                      capabilityRecovery(message._runtimeState.capabilityBlock)
                    }}
                  </div>
                </div>

                <div
                  v-if="message._runtimeState?.executionFailure"
                  class="runtime-block-card"
                  role="status"
                >
                  <div class="runtime-card-title">
                    {{ t('lens.chat.runtime.executionFailedTitle') }}
                  </div>
                  <div>
                    {{ executionFailureRecovery(message._runtimeState) }}
                  </div>
                </div>

                <div
                  v-if="
                    message._runtimeState?.outcome === 'partial' ||
                    (message._runtimeState?.outcome === 'blocked' &&
                      !message._runtimeState?.capabilityBlock &&
                      !message._runtimeState?.executionFailure)
                  "
                  class="runtime-outcome-card"
                  role="status"
                >
                  {{
                    message._runtimeState.outcome === 'blocked'
                      ? t('lens.chat.runtime.outcomeBlocked')
                      : t('lens.chat.runtime.outcomePartial')
                  }}
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
                          :aria-label="t('lens.chat.preview')"
                          @click="openPreview(file)"
                        >
                          <Eye :size="18" />
                        </button>
                        <button
                          type="button"
                          class="deliverable-action"
                          :title="t('lens.chat.download')"
                          :aria-label="t('lens.chat.download')"
                          @click="downloadOutputFile(file)"
                        >
                          <Download :size="18" />
                        </button>
                      </span>
                    </div>
                  </div>
                </div>

                <div class="message-time" :class="message.role">
                  {{ formatTime(getMessageTimestamp(message)) }}
                </div>

                <div
                  v-if="message.role === 'assistant'"
                  class="message-actions"
                >
                  <button
                    type="button"
                    class="icon-btn"
                    :title="t('common.copy')"
                    :aria-label="t('common.copy')"
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
                    v-if="!isAnonymous && message.run && message.content"
                    type="button"
                    class="icon-btn"
                    :class="{
                      'icon-btn-feedback-positive':
                        message.feedback === 'positive'
                    }"
                    :title="t('lens.chat.feedbackHelpful')"
                    :aria-label="t('lens.chat.feedbackHelpful')"
                    :aria-pressed="message.feedback === 'positive'"
                    :disabled="isFeedbackUpdating(message.run)"
                    @click="setFeedback(message, 'positive')"
                  >
                    <ThumbsUp :size="16" />
                  </button>
                  <button
                    v-if="!isAnonymous && message.run && message.content"
                    type="button"
                    class="icon-btn"
                    :class="{
                      'icon-btn-feedback-negative':
                        message.feedback === 'negative'
                    }"
                    :title="t('lens.chat.feedbackUnhelpful')"
                    :aria-label="t('lens.chat.feedbackUnhelpful')"
                    :aria-pressed="message.feedback === 'negative'"
                    :disabled="isFeedbackUpdating(message.run)"
                    @click="setFeedback(message, 'negative')"
                  >
                    <ThumbsDown :size="16" />
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
                    :aria-label="
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
                  <button
                    type="button"
                    class="icon-btn"
                    :title="t('lens.chat.retryAction')"
                    :aria-label="t('lens.chat.retryAction')"
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
                  v-if="isRunActive && liveStructuredProgress.items.length"
                  class="runtime-progress-card runtime-progress-live"
                  role="status"
                  aria-live="polite"
                >
                  <div class="runtime-card-title">
                    {{
                      progressTitle(
                        liveStructuredProgress.kind,
                        liveStructuredProgress.hasPlan
                      )
                    }}
                  </div>
                  <div
                    v-if="liveStructuredProgress.kind === 'workflow'"
                    class="runtime-workflow"
                  >
                    <div
                      v-for="task in liveStructuredProgress.tasks"
                      :key="task.id"
                      class="runtime-workflow-task"
                      :class="{
                        'is-direct': !liveStructuredProgress.hasPlan
                      }"
                    >
                      <div
                        v-if="liveStructuredProgress.hasPlan"
                        class="runtime-plan-step runtime-task-row"
                        :class="{
                          'is-active-ancestor': isActiveProgressAncestor(
                            task,
                            task.stages
                          )
                        }"
                      >
                        <span
                          class="runtime-plan-status"
                          :class="[
                            `is-${task.status}`,
                            {
                              'is-active-ancestor': isActiveProgressAncestor(
                                task,
                                task.stages
                              )
                            }
                          ]"
                          aria-hidden="true"
                        >
                          {{ progressStatusIcon(task.status) }}
                        </span>
                        <span>{{ workflowTaskTitle(task) }}</span>
                      </div>
                      <div
                        v-for="stage in task.stages"
                        :key="stage.id"
                        class="runtime-workflow-stage"
                      >
                        <div
                          class="runtime-plan-step runtime-stage-row"
                          :class="{
                            'is-active-ancestor': isActiveProgressAncestor(
                              stage,
                              stage.steps
                            )
                          }"
                        >
                          <span
                            class="runtime-plan-status"
                            :class="[
                              `is-${stage.status}`,
                              {
                                'is-active-ancestor': isActiveProgressAncestor(
                                  stage,
                                  stage.steps
                                )
                              }
                            ]"
                            aria-hidden="true"
                          >
                            {{ progressStatusIcon(stage.status) }}
                          </span>
                          <span>{{ workflowStageTitle(stage.kind) }}</span>
                        </div>
                        <div
                          :ref="
                            stage.status === 'in_progress'
                              ? 'liveActivityScrollRef'
                              : undefined
                          "
                          class="runtime-workflow-steps"
                        >
                          <div
                            v-for="step in stage.steps"
                            :key="step.id"
                            class="runtime-plan-step runtime-step-row"
                          >
                            <span
                              class="runtime-plan-status"
                              :class="`is-${step.status}`"
                              aria-hidden="true"
                            >
                              {{ progressStatusIcon(step.status) }}
                            </span>
                            <span>{{ workflowStepTitle(step) }}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div
                    v-else-if="liveStructuredProgress.kind === 'activity'"
                    ref="liveActivityScrollRef"
                    class="runtime-node-activities runtime-standalone-activities"
                  >
                    <div
                      v-for="activity in liveStructuredProgress.items"
                      :key="activity.id"
                      class="runtime-node-activity"
                    >
                      <span
                        class="runtime-activity-indicator"
                        :class="{
                          'is-current': isCurrentStandaloneActivity(
                            activity,
                            liveStructuredProgress.items
                          )
                        }"
                        aria-hidden="true"
                      >
                        {{
                          isCurrentStandaloneActivity(
                            activity,
                            liveStructuredProgress.items
                          )
                            ? ''
                            : '✓'
                        }}
                      </span>
                      <span>{{ activityLabel(activity.kind) }}</span>
                      <span
                        v-if="activity.count > 1"
                        class="runtime-activity-count"
                      >
                        ×{{ activity.count }}
                      </span>
                    </div>
                  </div>
                  <div
                    v-else
                    v-for="item in liveStructuredProgress.items"
                    :key="item.id"
                    class="runtime-plan-node"
                  >
                    <div class="runtime-plan-step">
                      <span
                        class="runtime-plan-status"
                        :class="`is-${item.status}`"
                        aria-hidden="true"
                      >
                        {{ progressStatusIcon(item.status) }}
                      </span>
                      <span class="runtime-step-content">
                        <span>{{ item.title }}</span>
                        <span v-if="item.summary" class="runtime-step-summary">
                          {{ item.summary }}
                        </span>
                      </span>
                    </div>
                    <div
                      v-if="nodeActivities(runtimeState, item.id).length"
                      :ref="
                        item.status === 'in_progress'
                          ? 'liveActivityScrollRef'
                          : undefined
                      "
                      class="runtime-node-activities"
                    >
                      <div
                        v-for="activity in nodeActivities(
                          runtimeState,
                          item.id
                        )"
                        :key="activity.id"
                        class="runtime-node-activity"
                      >
                        <span
                          class="runtime-activity-indicator"
                          :class="{
                            'is-current': isCurrentActivity(activity, item)
                          }"
                          aria-hidden="true"
                        >
                          {{ isCurrentActivity(activity, item) ? '' : '✓' }}
                        </span>
                        <span>{{ activityLabel(activity.kind) }}</span>
                        <span
                          v-if="activity.count > 1"
                          class="runtime-activity-count"
                        >
                          ×{{ activity.count }}
                        </span>
                      </div>
                    </div>
                  </div>
                  <div class="runtime-progress-footer">
                    <span>
                      {{
                        ['workflow', 'activity'].includes(
                          liveStructuredProgress.kind
                        )
                          ? structuredProgressText(runtimeState)
                          : liveProgressText
                      }}
                    </span>
                    <span v-if="elapsedText"> · {{ elapsedText }}</span>
                  </div>
                </div>

                <div
                  v-else-if="isRunActive"
                  class="live-status-card"
                  role="status"
                  aria-live="polite"
                >
                  <span class="live-progress-dot" />
                  <span class="live-status-text">
                    {{ liveProgressText }}
                  </span>
                  <span v-if="elapsedText" class="thinking-elapsed">
                    {{ elapsedText }}
                  </span>
                </div>

                <div
                  v-if="runtimeState.capabilityBlock"
                  class="runtime-block-card"
                  role="status"
                >
                  <div class="runtime-card-title">
                    {{ t('lens.chat.runtime.blockedTitle') }}
                  </div>
                  <div>
                    {{ capabilityRecovery(runtimeState.capabilityBlock) }}
                  </div>
                </div>

                <div
                  v-if="runtimeState.executionFailure"
                  class="runtime-block-card"
                  role="status"
                >
                  <div class="runtime-card-title">
                    {{ t('lens.chat.runtime.executionFailedTitle') }}
                  </div>
                  <div>
                    {{ executionFailureRecovery(runtimeState) }}
                  </div>
                </div>

                <div
                  v-if="runtimeState.artifacts.length"
                  class="runtime-artifact-card"
                  role="status"
                >
                  <div class="runtime-card-title">
                    {{ t('lens.chat.runtime.artifactTitle') }}
                  </div>
                  <div
                    v-for="artifact in runtimeState.artifacts"
                    :key="artifact.filename"
                  >
                    {{ artifact.filename }}
                  </div>
                </div>

                <div
                  v-if="
                    runtimeState.outcome === 'partial' ||
                    (runtimeState.outcome === 'blocked' &&
                      !runtimeState.capabilityBlock &&
                      !runtimeState.executionFailure)
                  "
                  class="runtime-outcome-card"
                  role="status"
                >
                  {{
                    runtimeState.outcome === 'blocked'
                      ? t('lens.chat.runtime.outcomeBlocked')
                      : t('lens.chat.runtime.outcomePartial')
                  }}
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
                    :title="t('lens.chat.removeImage')"
                    @click="removeAttachment(item)"
                  >
                    <span aria-hidden="true">×</span>
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
  Bell,
  MessagesSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
  Download,
  Eye,
  FileText,
  ThumbsDown,
  ThumbsUp
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
import { usePreferencesStore } from '@/store/preferences'
import { useUserStore } from '@/store/user'
import {
  answerCompletionTitle,
  clearUnreadSession,
  handleTerminalRun,
  pollRunUntilTerminal,
  readUnreadSessions,
  shouldReviewUnreadSession,
  UNREAD_STORAGE_KEY
} from '@/utils/answerCompletionNotifications'
import {
  activitiesForNode,
  applyRuntimeEvent,
  calculateRunElapsedSeconds,
  createRuntimeState,
  formatActivityProgressText,
  formatDuration,
  getMessageTimestamp,
  isActiveProgressAncestor,
  scrollConversationToBottomAfterRender,
  selectLiveProgressText,
  selectStructuredProgress,
  summarizePlanProgress,
  summarizeStageProgress,
  terminalSyncEvent,
  workflowProgressSource
} from '@/pages/lens/runtimeEvents'
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
  updateRunFeedback,
  uploadAttachment
} from '@/api/lens'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { showError, showSuccess, showWarning } = useToast()
const userStore = useUserStore()
const lensStore = useLensStore()
const preferencesStore = usePreferencesStore()

const assistants = ref([])
const sessions = ref([])
const messages = ref([])
const feedbackUpdatingRuns = ref(new Set())
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
const BASE_DOCUMENT_TITLE = document.title || 'SourceLens'
const streamError = ref('')
const failedRunError = ref(null)
const queuePosition = ref(null)
const currentRun = ref(null)
const unreadSessions = ref(readUnreadSessions(window.localStorage))
const loading = ref({ run: false })
const streamController = ref(null)
const sidebarOpen = ref(false)
const sidebarCollapsed = ref(false)
const deletingSessionUuid = ref('')
const renamingSessionUuid = ref('')
const renameDraft = ref('')
const composerRef = ref(null)
const scrollRef = ref(null)
const seenStepEventCounts = new Map()
const completionTrackers = new Map()
let sessionLoadGeneration = 0
const runtimeState = ref(createRuntimeState())
const liveActivityScrollRef = ref(null)
const elapsedSeconds = ref(0)
let elapsedTimer = null
let reviewingUnreadSession = false

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

const isGeneralChatAssistant = computed(
  () =>
    (selectedAssistant.value || publicAssistant.value)?.selected_task ===
    'general_chat'
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

const runtimePhaseText = computed(() => {
  const phase = runtimeState.value.phase
  if (!phase) return null
  const known = new Set([
    'analyzing',
    'planning',
    'executing',
    'answering',
    'completed'
  ])
  return known.has(phase) ? t(`lens.chat.runtime.phase.${phase}`) : null
})

const elapsedText = computed(() => {
  if (elapsedSeconds.value === 0) return null
  return formatDuration(elapsedSeconds.value)
})

function planProgressText(plan, durationSeconds = null, terminal = false) {
  const progress = summarizePlanProgress(plan, { terminal })
  if (!progress) return ''
  let text
  if (progress.isComplete) {
    text = t('lens.chat.runtime.planCompleted', progress)
  } else if (progress.isTerminal) {
    text = t('lens.chat.runtime.planEnded', progress)
  } else if (progress.currentTitle) {
    text = t('lens.chat.runtime.planProgressCurrent', progress)
  } else {
    text = t('lens.chat.runtime.planProgress', progress)
  }
  if (durationSeconds != null) {
    text += ` · ${formatDuration(durationSeconds)}`
  }
  return text
}

function stageProgressText(stages, durationSeconds = null, terminal = false) {
  const progress = summarizeStageProgress(stages, { terminal })
  if (!progress) return ''
  let text
  if (progress.isComplete) {
    text = t('lens.chat.runtime.stageCompleted', progress)
  } else if (progress.isTerminal) {
    text = t('lens.chat.runtime.stageEnded', progress)
  } else if (progress.currentTitle) {
    text = t('lens.chat.runtime.stageProgressCurrent', progress)
  } else {
    text = t('lens.chat.runtime.stageProgress', progress)
  }
  if (durationSeconds != null) {
    text += ` · ${formatDuration(durationSeconds)}`
  }
  return text
}

function structuredProgress(state) {
  return selectStructuredProgress({
    route: state?.route,
    plan: state?.plan,
    stages: state?.stages,
    activities: state?.activities,
    standaloneActivities: !isGeneralChatAssistant.value
  })
}

function structuredProgressText(
  state,
  durationSeconds = null,
  terminal = false
) {
  const progress = structuredProgress(state)
  if (progress.kind === 'plan') {
    return planProgressText(progress.items, durationSeconds, terminal)
  }
  if (progress.kind === 'stage') {
    return stageProgressText(progress.items, durationSeconds, terminal)
  }
  if (progress.kind === 'workflow') {
    const source = workflowProgressSource(progress.tasks, progress.hasPlan)
    if (source.kind === 'plan') {
      return planProgressText(source.items, durationSeconds, terminal)
    }
    return stageProgressText(source.items, durationSeconds, terminal)
  }
  if (progress.kind === 'activity') {
    return formatActivityProgressText(progress.items, {
      durationSeconds,
      terminal,
      translate: t
    })
  }
  return ''
}

function progressTitle(kind, hasPlan = false) {
  if (kind === 'plan') return t('lens.chat.runtime.planTitle')
  if (kind === 'activity') return t('lens.chat.agentActivity')
  if (kind === 'workflow') {
    return t(
      hasPlan ? 'lens.chat.runtime.planTitle' : 'lens.chat.runtime.stageTitle'
    )
  }
  return t('lens.chat.runtime.stageTitle')
}

const PATH_KINDS = new Set([
  'query_orders',
  'get_order_detail',
  'reading_order_commands',
  'checking_capability',
  'checking_tool',
  'checking_authentication',
  'authenticating',
  'querying_data',
  'count_results',
  'group_results',
  'analyzing_results',
  'summarizing_results'
])
function safePathKind(item) {
  let kind = PATH_KINDS.has(item?.kind) ? item.kind : 'querying_data'
  if (
    kind === 'query_orders' &&
    (!item.startDate || !item.endDate) &&
    !item.orderRef
  ) {
    kind = 'querying_data'
  }
  return kind
}

function workflowTaskTitle(task) {
  if (task.title) return task.title
  if (task.kind === 'get_order_detail') {
    return t(
      `lens.chat.runtime.workflow.task.${
        task.orderRef ? 'get_order_detail_ref' : 'get_order_detail'
      }`,
      { orderRef: task.orderRef }
    )
  }
  if (task.kind === 'query_orders') {
    return t(
      `lens.chat.runtime.workflow.task.${
        task.orderRef ? 'query_orders_ref' : 'query_orders'
      }`,
      { orderRef: task.orderRef }
    )
  }
  if (task.kind === 'analyze_results') {
    return t('lens.chat.runtime.workflow.task.analyze_results')
  }
  return t('lens.chat.runtime.workflow.task.query_data')
}

function workflowStageTitle(kind) {
  const known = new Set([
    'preparation',
    'order_query',
    'data_query',
    'result_analysis'
  ])
  const safeKind = known.has(kind) ? kind : 'data_query'
  return t(`lens.chat.runtime.workflow.stage.${safeKind}`)
}

function workflowStepTitle(item) {
  let kind = safePathKind(item)
  if (kind === 'get_order_detail' && item?.orderRef) {
    kind = 'get_order_detail_ref'
  } else if (kind === 'query_orders' && item?.orderRef) {
    kind = 'query_orders_ref'
  } else if (kind === 'summarizing_results' && item?.orderRef) {
    kind = 'summarizing_order'
  }
  return t(`lens.chat.runtime.pathStep.${kind}`, {
    startDate: item?.startDate,
    endDate: item?.endDate,
    orderRef: item?.orderRef
  })
}

function progressStatusIcon(status) {
  return {
    completed: '✓',
    in_progress: '●',
    pending: '○',
    failed: '×',
    skipped: '–'
  }[status]
}

const liveStructuredProgress = computed(() =>
  structuredProgress(runtimeState.value)
)

function nodeActivities(state, nodeId) {
  return activitiesForNode(state, nodeId)
}

function activityLabel(kind) {
  const known = new Set([
    'analyzingResults',
    'findingCapability',
    'preparingOutput',
    'queryingData',
    'readingContext',
    'readingSources',
    'searchingSources',
    'usingCapability'
  ])
  const safeKind = known.has(kind) ? kind : 'usingCapability'
  return t(`lens.chat.runtime.activity.${safeKind}`)
}

function isCurrentActivity(activity, item) {
  const latest = runtimeState.value.activities.at(-1)
  return item.status === 'in_progress' && latest?.id === activity.id
}

function isCurrentStandaloneActivity(activity, items) {
  return isRunActive.value && items.at(-1)?.id === activity.id
}

watch(
  () => runtimeState.value.activities.length,
  async () => {
    await nextTick()
    const refs = liveActivityScrollRef.value
    const target = Array.isArray(refs) ? refs.at(-1) : refs
    if (target) target.scrollTop = target.scrollHeight
  }
)

const livePlanProgressText = computed(() =>
  planProgressText(runtimeState.value.plan)
)

const liveStageProgressText = computed(() =>
  stageProgressText(runtimeState.value.stages)
)

const liveProgressText = computed(() =>
  selectLiveProgressText({
    planProgressText: livePlanProgressText.value,
    stageProgressText: runtimeState.value.route
      ? ''
      : liveStageProgressText.value,
    phaseText: runtimePhaseText.value,
    fallbackText: liveStatusText.value
  })
)

function runtimeStateFor(thinking) {
  let state = createRuntimeState()
  for (const event of thinking?.steps || []) {
    state = applyRuntimeEvent(state, event)
  }
  return applyRuntimeEvent(state, {
    type: 'done',
    outcome: thinking?.outcome,
    termination_detail: thinking?.termination_detail
  })
}

function capabilityRecovery(block) {
  const known = new Set([
    'capability',
    'configuration',
    'policy',
    'transient',
    'request',
    'tool',
    'verification'
  ])
  const errorType = known.has(block?.error_type) ? block.error_type : 'tool'
  return t(`lens.chat.runtime.recovery.${errorType}`)
}

function executionFailureRecovery(state) {
  return capabilityRecovery(state?.executionFailure)
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
      if (message.role === 'assistant' && message.thinking) {
        const runtime = runtimeStateFor(message.thinking)
        return { ...message, _runtimeState: runtime }
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
    const updateElapsedSeconds = () => {
      elapsedSeconds.value = calculateRunElapsedSeconds(currentRun.value)
    }
    updateElapsedSeconds()
    elapsedTimer = setInterval(() => {
      updateElapsedSeconds()
    }, 1000)
  } else {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
})

watch(
  [
    () => preferencesStore.answerCompletionIndicator,
    () => preferencesStore.currentLanguage
  ],
  refreshUnreadSessions
)

const { isMobile } = useIsMobile()

function authHeaders() {
  const token = localStorage.getItem('access_token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function resetStreamState() {
  streamController.value?.abort()
  partialAnswer.value = ''
  streamError.value = ''
  failedRunError.value = null
  queuePosition.value = null
  runtimeState.value = createRuntimeState()
  elapsedSeconds.value = 0
  seenStepEventCounts.clear()
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function refreshUnreadSessions() {
  unreadSessions.value = readUnreadSessions(window.localStorage)
  const hasUnread =
    preferencesStore.answerCompletionIndicator &&
    Object.keys(unreadSessions.value).length > 0
  document.title = answerCompletionTitle({
    baseTitle: BASE_DOCUMENT_TITLE,
    completionLabel: t('lens.chat.tabAnswerCompleted'),
    hasUnread
  })
}

function sessionHasUnreadAnswer(sessionUuid) {
  return (
    preferencesStore.answerCompletionIndicator &&
    selectedSessionUuid.value !== sessionUuid &&
    Boolean(unreadSessions.value[sessionUuid])
  )
}

function handleCompletionStorage(event) {
  if (event.key === UNREAD_STORAGE_KEY) {
    refreshUnreadSessions()
  }
  if (event.key === 'answerCompletionIndicator') {
    preferencesStore.answerCompletionIndicator = event.newValue !== 'false'
    refreshUnreadSessions()
  }
}

function handleCompletionVisibility() {
  const sessionUuid = selectedSessionUuid.value
  if (
    reviewingUnreadSession ||
    !shouldReviewUnreadSession({
      documentRef: document,
      selectedSessionUuid: sessionUuid,
      unreadSessions: unreadSessions.value
    })
  ) {
    return
  }
  reviewingUnreadSession = true
  void selectSession({ uuid: sessionUuid }, false).finally(() => {
    reviewingUnreadSession = false
  })
}

function startCompletionTracking(run, sessionUuid) {
  if (!run?.uuid || completionTrackers.has(run.uuid)) {
    return
  }

  const tracker = { stopped: false }
  completionTrackers.set(run.uuid, tracker)
  void pollRunUntilTerminal({
    getRun,
    initialRun: run,
    isStopped: () => tracker.stopped,
    maxAttempts: RUN_POLL_MAX_ATTEMPTS,
    runUuid: run.uuid,
    sleep: () => sleep(RUN_POLL_INTERVAL_MS)
  })
    .then((terminalRun) => {
      if (!terminalRun || tracker.stopped) return
      const result = handleTerminalRun({
        documentRef: document,
        indicatorEnabled: preferencesStore.answerCompletionIndicator,
        run: terminalRun,
        selectedSessionUuid: selectedSessionUuid.value,
        sessionUuid,
        storage: window.localStorage
      })
      if (result.unreadChanged) {
        refreshUnreadSessions()
      }
    })
    .finally(() => completionTrackers.delete(run.uuid))
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

function pushAgentActivity(item) {
  runtimeState.value = applyRuntimeEvent(runtimeState.value, item)
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
    const getScrollContainer = () => scrollRef.value
    await scrollConversationToBottomAfterRender(getScrollContainer, nextTick)
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

  let session
  try {
    session = await createSession({
      assistant_uuid: selectedAssistant.value.uuid,
      title: ''
    })
  } catch {
    showError(t('lens.chat.sessionCreateFailed'))
    return null
  }

  sessions.value = [session, ...sessions.value]
  selectedSessionUuid.value = session.uuid
  question.value = ''
  if (composerRef.value) composerRef.value.style.height = 'auto'
  clearAttachments()
  messages.value = []
  currentRun.value = null
  resetStreamState()
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
  const loadGeneration = ++sessionLoadGeneration
  const isCurrentLoad = () =>
    loadGeneration === sessionLoadGeneration &&
    selectedSessionUuid.value === session.uuid
  const sessionChanged = selectedSessionUuid.value !== session.uuid
  mySharesOpen.value = false
  clearAttachments()
  selectedSessionUuid.value = session.uuid
  let loadedMessages
  try {
    loadedMessages = await listMessages(session.uuid)
  } catch (error) {
    if (!isCurrentLoad()) return
    if ([403, 404].includes(error?.response?.status)) {
      showError(t('lens.chat.sessionAccessDenied'))
      return
    }
    throw error
  }
  if (!isCurrentLoad()) return
  messages.value = loadedMessages
  // Session history is ready for display. An active run's SSE can stay open
  // for minutes, so it must not keep the whole chat behind the page loader.
  booted.value = true
  if (sessionChanged) {
    question.value = ''
    if (composerRef.value) composerRef.value.style.height = 'auto'
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
  if (!isCurrentLoad()) return
  await maybeResumeActiveRun(session.uuid)
  if (!isCurrentLoad()) return
  if (clearUnreadSession(window.localStorage, session.uuid)) {
    refreshUnreadSessions()
  }
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
  startCompletionTracking(run, sessionUuid)
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
  runtimeState.value = applyRuntimeEvent(runtimeState.value, event)
  if (event.type === 'sync' || event.type === 'status') {
    currentRun.value = { ...currentRun.value, status: event.status }
    if (event.status !== 'queued') queuePosition.value = null
    if (event.type === 'sync') {
      event.steps?.forEach((step) => handleStepEvent(step, event.ts))
    }
    const terminalEvent = terminalSyncEvent(event)
    if (terminalEvent) {
      runtimeState.value = applyRuntimeEvent(runtimeState.value, terminalEvent)
    }
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
    partialAnswer.value = ''
  }
  if (event.type === 'token') {
    appendAnswerDelta(event.content)
  }
  if (event.type === 'error') {
    streamError.value = event.error?.code
      ? mapRunError(event.error.code)
      : event.error?.message || event.error || t('lens.chat.events.error')
  }
}

function handleStepEvent(event) {
  const events = event.detail?.events || []
  const stepKey = event.sequence || event.step || 'step'
  const seenCount = seenStepEventCounts.get(stepKey) || 0
  const newEvents = events.slice(seenCount)
  seenStepEventCounts.set(stepKey, events.length)

  newEvents.forEach(pushAgentActivity)
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
    startCompletionTracking(run, sessionAtSubmit)
    // switched away between createRun and here — don't bind this run's live
    // state onto the now-current assistant
    if (selectedSessionUuid.value !== sessionAtSubmit) return
    currentRun.value = run
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

function isFeedbackUpdating(runUuid) {
  return feedbackUpdatingRuns.value.has(runUuid)
}

async function setFeedback(message, feedback) {
  const runUuid = message?.run
  if (!runUuid || isFeedbackUpdating(runUuid)) return
  const nextFeedback = message.feedback === feedback ? '' : feedback
  feedbackUpdatingRuns.value = new Set([...feedbackUpdatingRuns.value, runUuid])
  try {
    const result = await updateRunFeedback(runUuid, nextFeedback)
    messages.value = messages.value.map((item) =>
      item.uuid === message.uuid
        ? {
            ...item,
            feedback: result.feedback,
            feedback_updated_at: result.feedback_updated_at
          }
        : item
    )
  } catch {
    showError(t('lens.chat.feedbackFailed'))
  } finally {
    const updating = new Set(feedbackUpdatingRuns.value)
    updating.delete(runUuid)
    feedbackUpdatingRuns.value = updating
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
    if (clearUnreadSession(window.localStorage, session.uuid)) {
      refreshUnreadSessions()
    }
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
  window.addEventListener('storage', handleCompletionStorage)
  window.addEventListener('focus', handleCompletionVisibility)
  document.addEventListener('visibilitychange', handleCompletionVisibility)
  refreshUnreadSessions()
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
  window.removeEventListener('storage', handleCompletionStorage)
  window.removeEventListener('focus', handleCompletionVisibility)
  document.removeEventListener('visibilitychange', handleCompletionVisibility)
  document.title = BASE_DOCUMENT_TITLE
  completionTrackers.forEach((tracker) => {
    tracker.stopped = true
  })
  completionTrackers.clear()
  streamController.value?.abort()
  clearInterval(elapsedTimer)
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

.session-unread-indicator {
  @apply flex h-6 w-6 shrink-0 items-center justify-center rounded-full;
  @apply bg-primary-50 text-primary-600;
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
  @apply mx-auto w-full max-w-[860px] px-5 py-7;
  padding-bottom: 220px;
}

.message-row {
  @apply mb-8 flex items-start gap-3;
}

.message-row-user {
  @apply flex-row-reverse;
}

.message-avatar {
  @apply flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-[11px] font-semibold;
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
  max-width: min(620px, calc(100% - 40px));
}

.message-card {
  @apply min-w-0;
}

.message-card.user {
  @apply rounded-xl px-3.5 py-2.5 text-left;
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
  @apply mb-2.5 text-[15px] leading-6;
  color: #374151;
}

.message-markdown :deep(.markdown-content ul),
.message-markdown :deep(.markdown-content ol) {
  @apply mb-3 pl-5;
}

.message-markdown :deep(.markdown-content li) {
  @apply mb-1.5 text-[15px] leading-6;
  color: #374151;
}

.message-markdown :deep(.markdown-content :not(pre) > code) {
  background: #eef4fe;
  color: #0e278c;
}

.message-text {
  @apply whitespace-pre-wrap break-words text-[15px] leading-6;
  color: #111827;
}

.message-actions {
  @apply mt-2 flex items-center gap-1;
}

.icon-btn {
  @apply flex h-[30px] w-[30px] items-center justify-center rounded-md transition-colors;
  color: #9ca3af;
}

.icon-btn:hover {
  background: #f3f4f6;
  color: #374151;
}

.icon-btn:disabled {
  @apply cursor-wait opacity-60;
}

.icon-btn-feedback-positive {
  background: #dcfce7;
  color: #15803d;
}

.icon-btn-feedback-positive:hover {
  background: #bbf7d0;
  color: #166534;
}

.icon-btn-feedback-negative {
  background: #fee2e2;
  color: #b91c1c;
}

.icon-btn-feedback-negative:hover {
  background: #fecaca;
  color: #991b1b;
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

.live-status-text {
  @apply min-w-0 truncate;
}

.thinking-elapsed {
  @apply shrink-0 text-xs tabular-nums;
  color: #9ca3af;
}

.runtime-progress-card,
.runtime-block-card,
.runtime-artifact-card,
.runtime-outcome-card {
  margin-top: 0.5rem;
  border: 1px solid #e2e8f0;
  border-radius: 0.625rem;
  background: #f8fafc;
  padding: 0.65rem 0.75rem;
  color: #475569;
  font-size: 0.78rem;
  line-height: 1.45;
}

.runtime-progress-card {
  margin-top: 0;
  margin-bottom: 0.5rem;
}

.runtime-progress-live {
  border-color: #d8dce8;
  background: #f8f9fc;
}

.runtime-progress-summary {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  list-style: none;
}

.runtime-progress-summary::-webkit-details-marker {
  display: none;
}

.runtime-progress-summary .runtime-card-title {
  margin-bottom: 0;
}

.runtime-progress-summary-text {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: #64748b;
  font-size: 0.72rem;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.runtime-progress-chevron {
  flex: 0 0 auto;
  color: #94a3b8;
  font-size: 0.9rem;
  transition: transform 0.15s ease;
}

.runtime-progress-card[open] .runtime-progress-summary {
  margin-bottom: 0.35rem;
}

.runtime-progress-card[open] .runtime-progress-chevron {
  transform: rotate(180deg);
}

.runtime-card-title {
  margin-bottom: 0.35rem;
  color: #334155;
  font-weight: 600;
}

.runtime-plan-step {
  display: flex;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.18rem 0;
}

.runtime-workflow-task + .runtime-workflow-task {
  margin-top: 0.3rem;
}

.runtime-task-row {
  color: #334155;
  font-weight: 600;
}

.runtime-workflow-stage {
  margin-left: 1.45rem;
  border-left: 1px solid #dbe3ec;
  padding-left: 0.65rem;
}

.runtime-workflow-task.is-direct .runtime-workflow-stage {
  margin-left: 0;
}

.runtime-stage-row {
  color: #475569;
  font-weight: 500;
}

.runtime-workflow-steps {
  max-height: 6.5rem;
  margin-left: 1.35rem;
  overflow-y: auto;
  color: #64748b;
  font-size: 0.72rem;
  scrollbar-width: thin;
}

.runtime-step-row {
  padding: 0.12rem 0;
}

.runtime-node-activities {
  max-height: 5.5rem;
  margin: 0.15rem 0 0.25rem 1.5rem;
  padding: 0.15rem 0.35rem;
  overflow-y: auto;
  border-left: 1px solid #e2e8f0;
  color: #64748b;
  font-size: 0.71rem;
  scrollbar-width: thin;
}

.runtime-standalone-activities {
  margin-left: 0;
}

.runtime-node-activity {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  min-height: 1.3rem;
}

.runtime-activity-indicator {
  display: inline-flex;
  width: 0.75rem;
  height: 0.75rem;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  color: #6b8b77;
  font-size: 0.62rem;
}

.runtime-activity-indicator.is-current {
  border: 1.5px solid #d8dce8;
  border-top-color: #6677a3;
  border-radius: 9999px;
  animation: spin 0.75s linear infinite;
}

.runtime-activity-count {
  flex: 0 0 auto;
  color: #9a9388;
}

.runtime-plan-status {
  display: inline-flex;
  width: 1rem;
  height: 1rem;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  margin-top: 0.08rem;
  color: #8b8378;
  font-size: 0.75rem;
  font-weight: 700;
  line-height: 1;
}

.runtime-plan-status.is-in_progress {
  width: 0.85rem;
  height: 0.85rem;
  margin: 0.15rem 0.075rem 0;
  border: 2px solid #ead7b4;
  border-top-color: #b7791f;
  border-radius: 9999px;
  color: transparent;
  font-size: 0;
  animation: spin 0.75s linear infinite;
}

.runtime-plan-step.is-active-ancestor {
  color: #74521e;
  font-weight: 600;
}

.runtime-plan-status.is-in_progress.is-active-ancestor {
  border: 0;
  animation: none;
}

.runtime-plan-status.is-completed {
  color: #3f7a5c;
}

.runtime-plan-status.is-failed {
  color: #b64949;
}

.runtime-plan-status.is-skipped {
  color: #9ca3af;
}

.runtime-step-content {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.runtime-step-summary {
  margin-top: 0.08rem;
  color: #7a746a;
  font-size: 0.72rem;
}

.runtime-progress-footer {
  margin-top: 0.4rem;
  padding-top: 0.4rem;
  border-top: 1px dashed #e2e8f0;
  color: #64748b;
  font-size: 0.72rem;
}

.live-status-card {
  @apply mb-2 flex items-center gap-2 rounded-lg px-3 py-2 text-sm;
  border: 1px solid #e5e7eb;
  background: #f9fafb;
  color: #374151;
}

.runtime-block-card {
  border-color: #e8c78f;
  background: #fff8e8;
  color: #74521e;
}

.runtime-outcome-card {
  border-color: #d5c8ae;
  background: #f7f1e4;
}

.live-progress-dot {
  @apply h-1.5 w-1.5 shrink-0 rounded-full;
  background: #2b4ee6;
  animation: cursor-blink 1s steps(2, start) infinite;
}

.live-text {
  @apply whitespace-pre-wrap text-[15px] leading-6;
  color: #111827;
}

.live-thinking {
  @apply flex items-center gap-2 text-sm;
  color: #4b5563;
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
  @apply mx-auto w-full max-w-[860px];
}

.composer-shell {
  @apply pointer-events-auto;
}

.composer {
  @apply flex items-center gap-3 rounded-xl border bg-white px-4 py-2.5;
  border-color: #dbe1e8;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
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
  @apply absolute inset-0 m-auto h-5 w-5 rounded-full border-2
    border-gray-300 border-t-primary-500;
  animation: spin 0.7s linear infinite;
}

.composer-thumb-remove {
  @apply absolute right-0.5 top-0.5 flex h-5 w-5 items-center justify-center;
}

.composer-thumb-remove span {
  @apply flex h-5 w-5 items-center justify-center rounded-full bg-black/55
    text-sm leading-none text-white;
}

@media (max-width: 767px), (hover: none), (pointer: coarse) {
  .sidebar-collapse-btn,
  .composer-action-btn,
  .session-delete-btn,
  .session-action-btn,
  .session-rename-btn,
  .icon-btn,
  .composer-attach-btn,
  .composer-thumb-remove {
    @apply h-11 w-11;
  }

  .deliverable-action,
  .retry-hint-btn {
    min-width: 44px;
    min-height: 44px;
  }

  .session-delete-btn,
  .session-rename-btn {
    @apply opacity-100;
  }

  .composer-thumb-remove {
    top: 0;
    right: 0;
  }

  .message-actions {
    flex-wrap: wrap;
  }
}

.session-delete-btn:focus-visible,
.session-rename-btn:focus-visible {
  @apply opacity-100;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .runtime-plan-status.is-in_progress,
  .runtime-activity-indicator.is-current {
    animation: none;
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

  .sidebar.sidebar-open {
    transform: translateX(0);
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
    @apply px-4 py-5;
    padding-bottom: 220px;
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
