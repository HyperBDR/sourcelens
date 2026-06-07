<template>
  <div class="min-h-screen bg-slate-950 text-slate-100">
    <div class="pointer-events-none fixed inset-0 overflow-hidden">
      <div
        class="absolute left-[-12rem] top-[-10rem] h-80 w-80 rounded-full bg-cyan-500/20 blur-3xl"
      />
      <div
        class="absolute right-[-8rem] top-24 h-72 w-72 rounded-full bg-fuchsia-500/20 blur-3xl"
      />
      <div
        class="absolute bottom-[-10rem] left-1/3 h-96 w-96 rounded-full bg-emerald-500/10 blur-3xl"
      />
    </div>

    <div class="relative mx-auto max-w-[1600px] px-4 py-6 lg:px-6 xl:px-8">
      <header
        class="mb-6 overflow-hidden rounded-[28px] border border-white/10 bg-white/6 shadow-2xl backdrop-blur-xl"
      >
        <div class="grid gap-6 px-6 py-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div class="space-y-4">
            <div class="flex flex-wrap items-center gap-3">
              <span
                class="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-cyan-200"
              >
                AI Query MVP
              </span>
              <span
                class="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-200"
              >
                REST + SSE
              </span>
              <span
                class="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-200"
              >
                `/api/lens/*`
              </span>
            </div>

            <div class="space-y-2">
              <h1 class="text-3xl font-semibold tracking-tight text-white">
                AI Query 系统前端
              </h1>
              <p class="max-w-4xl text-sm leading-6 text-slate-300">
                这个页面直接联动后端 Lens API，覆盖 assistant / session / run /
                system-health 的核心闭环。它保留原型的视觉方向，
                但所有关键数据都来自真实接口。
              </p>
            </div>

            <div class="grid gap-3 md:grid-cols-4">
              <div
                v-for="metric in topMetrics"
                :key="metric.label"
                class="rounded-2xl border border-white/10 bg-slate-900/70 p-4"
              >
                <div class="text-xs text-slate-400">
                  {{ metric.label }}
                </div>
                <div class="mt-2 text-2xl font-semibold text-white">
                  {{ metric.value }}
                </div>
                <div class="mt-1 text-xs text-slate-500">
                  {{ metric.help }}
                </div>
              </div>
            </div>
          </div>

          <div class="space-y-4">
            <div class="rounded-3xl border border-white/10 bg-slate-900/80 p-4">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <div
                    class="text-xs uppercase tracking-[0.2em] text-slate-500"
                  >
                    当前上下文
                  </div>
                  <div class="mt-1 text-base font-semibold text-white">
                    {{ selectedAssistant?.name || '等待加载' }}
                  </div>
                </div>
                <StatusBadge :status="selectedAssistant?.status || 'pending'" />
              </div>

              <div class="mt-4 flex flex-wrap gap-2">
                <BaseButton
                  variant="outline"
                  size="sm"
                  :loading="loading.bootstrap"
                  @click="bootstrap"
                >
                  刷新数据
                </BaseButton>
                <BaseButton
                  variant="secondary"
                  size="sm"
                  :disabled="!selectedSession"
                  @click="refreshSession"
                >
                  刷新会话
                </BaseButton>
              </div>

              <div class="mt-4 grid gap-2">
                <button
                  v-for="scope in scopes"
                  :key="scope.key"
                  class="group flex items-start justify-between rounded-2xl border px-3 py-2 text-left transition"
                  :class="
                    activeScope === scope.key
                      ? 'border-cyan-400/50 bg-cyan-400/10'
                      : 'border-white/10 bg-white/5 hover:bg-white/8'
                  "
                  @click="activeScope = scope.key"
                >
                  <div>
                    <div class="text-sm font-medium text-white">
                      {{ scope.label }}
                    </div>
                    <div class="mt-1 text-xs text-slate-400">
                      {{ scope.hint }}
                    </div>
                  </div>
                  <span
                    class="mt-0.5 rounded-full border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.2em] text-slate-400"
                  >
                    {{ scope.key }}
                  </span>
                </button>
              </div>
            </div>

            <div class="rounded-3xl border border-white/10 bg-slate-900/80 p-4">
              <div class="text-xs uppercase tracking-[0.2em] text-slate-500">
                深链
              </div>
              <div class="mt-1 text-sm text-slate-300">
                assistant={{ route.query.assistant || 'auto' }}, session={{
                  route.query.session || 'auto'
                }}
              </div>
            </div>
          </div>
        </div>
      </header>

      <div class="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
        <aside class="space-y-6">
          <BaseCard
            padding="none"
            class="overflow-hidden border border-white/10 bg-slate-900/80 shadow-none"
          >
            <template #header>
              <div class="flex items-center justify-between gap-3">
                <div>
                  <h2 class="text-base font-semibold text-white">Assistants</h2>
                  <p class="mt-1 text-xs text-slate-400">
                    选择一个助手后加载会话与绑定信息。
                  </p>
                </div>
                <StatusBadge
                  :status="assistants.length ? 'success' : 'disabled'"
                />
              </div>
            </template>

            <div class="space-y-3 p-4">
              <div v-if="assistants.length" class="space-y-2">
                <button
                  v-for="assistant in assistants"
                  :key="assistant.uuid"
                  class="w-full rounded-3xl border p-4 text-left transition"
                  :class="
                    selectedAssistant?.uuid === assistant.uuid
                      ? 'border-cyan-400/50 bg-cyan-400/10'
                      : 'border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/8'
                  "
                  @click="selectAssistant(assistant)"
                >
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                      <div class="truncate text-sm font-semibold text-white">
                        {{ assistant.name }}
                      </div>
                      <div class="mt-1 text-xs text-slate-400">
                        {{ assistant.slug }} ·
                        {{ assistant.selected_task || '-' }}
                      </div>
                    </div>
                    <StatusBadge :status="assistant.status" />
                  </div>

                  <div class="mt-3 grid gap-2 text-xs text-slate-400">
                    <div class="flex items-center justify-between gap-3">
                      <span>Skills</span>
                      <span
                        >{{ assistant.skill_summary?.enabled || 0 }}/{{
                          assistant.skill_summary?.total || 0
                        }}</span
                      >
                    </div>
                    <div class="flex items-center justify-between gap-3">
                      <span>MCP</span>
                      <span
                        >{{ assistant.mcp_summary?.enabled || 0 }}/{{
                          assistant.mcp_summary?.total || 0
                        }}</span
                      >
                    </div>
                    <div class="flex items-center justify-between gap-3">
                      <span>Dirs</span>
                      <span>{{ assistant.selected_dirs?.length || 0 }}</span>
                    </div>
                  </div>
                </button>
              </div>

              <div
                v-else
                class="rounded-3xl border border-dashed border-white/15 bg-white/4 px-4 py-10 text-center"
              >
                <div class="text-sm font-medium text-white">暂无 assistant</div>
                <div class="mt-1 text-xs leading-5 text-slate-400">
                  请先在后端创建一个 assistant 记录。
                </div>
              </div>
            </div>
          </BaseCard>

          <BaseCard
            padding="none"
            class="overflow-hidden border border-white/10 bg-slate-900/80 shadow-none"
          >
            <template #header>
              <div class="flex items-center justify-between gap-3">
                <div>
                  <h2 class="text-base font-semibold text-white">Sessions</h2>
                  <p class="mt-1 text-xs text-slate-400">
                    支持按 assistant 深链定位会话。
                  </p>
                </div>
                <BaseButton
                  variant="secondary"
                  size="sm"
                  :disabled="!selectedAssistant || loading.sessions"
                  @click="createStarterSession"
                >
                  新建
                </BaseButton>
              </div>
            </template>

            <div class="space-y-3 p-4">
              <div v-if="sessions.length" class="space-y-2">
                <button
                  v-for="session in sessions"
                  :key="session.uuid"
                  class="w-full rounded-3xl border p-4 text-left transition"
                  :class="
                    selectedSession?.uuid === session.uuid
                      ? 'border-cyan-400/50 bg-cyan-400/10'
                      : 'border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/8'
                  "
                  @click="selectSession(session)"
                >
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                      <div class="truncate text-sm font-semibold text-white">
                        {{ session.title || '未命名会话' }}
                      </div>
                      <div class="mt-1 text-xs text-slate-400">
                        {{ formatClock(session.created_at) }}
                      </div>
                    </div>
                    <StatusBadge :status="session.status" />
                  </div>
                </button>
              </div>

              <div
                v-else
                class="rounded-3xl border border-dashed border-white/15 bg-white/4 px-4 py-10 text-center"
              >
                <div class="text-sm font-medium text-white">没有会话</div>
                <div class="mt-1 text-xs leading-5 text-slate-400">
                  点击“新建”会自动创建第一条会话，方便直接进入查询。
                </div>
              </div>
            </div>
          </BaseCard>
        </aside>

        <main class="space-y-6">
          <BaseCard
            padding="none"
            class="overflow-hidden border border-white/10 bg-slate-900/80 shadow-none"
          >
            <template #header>
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 class="text-base font-semibold text-white">查询与流式</h2>
                  <p class="mt-1 text-xs text-slate-400">
                    创建 queued run，并通过 SSE 同步阶段和答案。
                  </p>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                  <StatusBadge :status="currentRun?.status || 'pending'" />
                  <span
                    class="rounded-full border border-white/10 px-2.5 py-1 text-[11px] text-slate-400"
                  >
                    {{ currentRun?.uuid || 'no-run' }}
                  </span>
                </div>
              </div>
            </template>

            <div class="space-y-4 p-4">
              <div class="grid gap-4 md:grid-cols-2">
                <label class="space-y-2 text-sm text-slate-300">
                  <span
                    class="text-xs uppercase tracking-[0.2em] text-slate-500"
                  >
                    执行方式
                  </span>
                  <label
                    class="flex min-h-[42px] items-center gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 text-sm"
                  >
                    <input
                      v-model="runInline"
                      type="checkbox"
                      class="h-4 w-4 rounded border-white/20 bg-slate-900"
                    />
                    <span class="text-slate-300">同步执行</span>
                  </label>
                </label>

                <label class="space-y-2 text-sm text-slate-300">
                  <span
                    class="text-xs uppercase tracking-[0.2em] text-slate-500"
                  >
                    目标助手
                  </span>
                  <select
                    v-model="selectedAssistantUuid"
                    class="input"
                    @change="handleAssistantChange"
                  >
                    <option
                      v-for="assistant in assistants"
                      :key="assistant.uuid"
                      :value="assistant.uuid"
                    >
                      {{ assistant.name }}
                    </option>
                  </select>
                </label>
              </div>

              <label class="space-y-2 text-sm text-slate-300">
                <span class="text-xs uppercase tracking-[0.2em] text-slate-500">
                  问题
                </span>
                <textarea
                  v-model="question"
                  rows="5"
                  class="input resize-none"
                  placeholder="输入一个需要检索的问题"
                />
              </label>

              <div class="flex flex-wrap gap-2">
                <BaseButton
                  variant="primary"
                  :loading="loading.run"
                  :disabled="!selectedSession"
                  @click="startQuery"
                >
                  提交查询
                </BaseButton>
                <BaseButton
                  variant="secondary"
                  :disabled="!canCancelRun"
                  @click="cancelCurrentRun"
                >
                  中止
                </BaseButton>
                <BaseButton variant="outline" @click="resetQuery">
                  清空
                </BaseButton>
              </div>
            </div>
          </BaseCard>

          <div
            class="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]"
          >
            <BaseCard
              padding="none"
              class="overflow-hidden border border-white/10 bg-slate-900/80 shadow-none"
            >
              <template #header>
                <div class="flex items-center justify-between gap-3">
                  <div>
                    <h3 class="text-sm font-semibold text-white">对话记录</h3>
                    <p class="mt-1 text-xs text-slate-400">
                      由 `/sessions/:uuid/messages` 返回的真实消息。
                    </p>
                  </div>
                  <span
                    class="rounded-full border border-white/10 px-2.5 py-1 text-[11px] text-slate-400"
                  >
                    {{ messages.length }} 条
                  </span>
                </div>
              </template>

              <div class="space-y-3 p-4">
                <div v-if="messages.length" class="space-y-3">
                  <article
                    v-for="message in messages"
                    :key="message.uuid"
                    class="rounded-3xl border border-white/10 p-4"
                    :class="
                      message.role === 'assistant'
                        ? 'bg-cyan-400/6'
                        : 'bg-white/5'
                    "
                  >
                    <div class="flex items-center justify-between gap-3">
                      <div
                        class="text-xs uppercase tracking-[0.2em] text-slate-500"
                      >
                        {{ message.role }}
                      </div>
                      <div class="text-[11px] text-slate-500">
                        {{ message.sequence }}
                      </div>
                    </div>
                    <div
                      class="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-200"
                    >
                      {{ message.content || '（空）' }}
                    </div>
                    <div
                      v-if="message.run"
                      class="mt-3 text-[11px] text-slate-500"
                    >
                      run: {{ message.run }}
                    </div>
                  </article>
                </div>

                <div
                  v-else
                  class="rounded-3xl border border-dashed border-white/15 bg-white/4 px-4 py-10 text-center"
                >
                  <div class="text-sm font-medium text-white">暂无消息</div>
                  <div class="mt-1 text-xs leading-5 text-slate-400">
                    创建会话并提交查询后，这里会展示消息流。
                  </div>
                </div>
              </div>
            </BaseCard>

            <BaseCard
              padding="none"
              class="overflow-hidden border border-white/10 bg-slate-900/80 shadow-none"
            >
              <template #header>
                <div>
                  <h3 class="text-sm font-semibold text-white">Run / SSE</h3>
                  <p class="mt-1 text-xs text-slate-400">
                    展示 running / failed / cancelled 的 API 数据流。
                  </p>
                </div>
              </template>

              <div class="space-y-4 p-4">
                <div
                  class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div>
                      <div class="text-sm font-semibold text-white">
                        当前状态
                      </div>
                      <div class="mt-1 text-xs text-slate-400">
                        {{ runStateLabel }}
                      </div>
                    </div>
                    <StatusBadge :status="badgeStatus" />
                  </div>

                  <div
                    class="mt-4 h-2 overflow-hidden rounded-full bg-white/10"
                  >
                    <div
                      class="h-full rounded-full bg-gradient-to-r from-cyan-400 via-sky-400 to-emerald-400 transition-all duration-300"
                      :style="{ width: `${progress}%` }"
                    />
                  </div>
                  <div
                    class="mt-2 flex items-center justify-between text-[11px] text-slate-500"
                  >
                    <span>{{ progress }}%</span>
                    <span>{{ currentRun?.status || 'pending' }}</span>
                  </div>
                </div>

                <BaseLoading
                  v-if="loading.stream"
                  text="SSE 正在持续输出中"
                  variant="primary"
                />

                <div class="space-y-2">
                  <div
                    class="text-xs uppercase tracking-[0.2em] text-slate-500"
                  >
                    事件时间线
                  </div>
                  <div v-if="runEvents.length" class="space-y-2">
                    <div
                      v-for="event in runEvents"
                      :key="event.id"
                      class="rounded-2xl border border-white/10 bg-white/5 p-3"
                    >
                      <div class="flex items-center justify-between gap-3">
                        <div class="flex items-center gap-2">
                          <span
                            class="h-2.5 w-2.5 rounded-full"
                            :class="eventDotClass(event.type)"
                          />
                          <span class="text-sm font-medium text-white">
                            {{ event.title }}
                          </span>
                        </div>
                        <span class="text-[11px] text-slate-500">
                          {{ event.time }}
                        </span>
                      </div>
                      <div class="mt-2 text-xs leading-5 text-slate-400">
                        {{ event.detail }}
                      </div>
                    </div>
                  </div>

                  <div
                    v-else
                    class="rounded-3xl border border-dashed border-white/15 bg-white/4 px-4 py-10 text-center"
                  >
                    <div class="text-sm font-medium text-white">
                      暂无流式事件
                    </div>
                    <div class="mt-1 text-xs leading-5 text-slate-400">
                      点击“提交查询”后会从 SSE 流读取事件。
                    </div>
                  </div>
                </div>

                <div class="grid gap-3 lg:grid-cols-2">
                  <div
                    class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                  >
                    <div class="text-sm font-semibold text-white">部分答案</div>
                    <div
                      class="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-200"
                    >
                      {{ partialAnswer || '等待生成部分答案……' }}
                    </div>
                  </div>

                  <div
                    class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                  >
                    <div class="text-sm font-semibold text-white">
                      最终答案 / 错误
                    </div>
                    <div
                      class="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-200"
                    >
                      {{
                        finalAnswer || streamError || '成功时这里展示完整回答。'
                      }}
                    </div>
                  </div>
                </div>
              </div>
            </BaseCard>
          </div>
        </main>

        <aside class="space-y-6">
          <BaseCard
            padding="none"
            class="overflow-hidden border border-white/10 bg-slate-900/80 shadow-none"
          >
            <template #header>
              <div>
                <h2 class="text-base font-semibold text-white">
                  Admin Snapshots
                </h2>
                <p class="mt-1 text-xs text-slate-400">
                  数据源、技能、MCP、全局设置与系统健康。
                </p>
              </div>
            </template>

            <div class="space-y-4 p-4">
              <div
                class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
              >
                <div class="flex items-center justify-between gap-3">
                  <div>
                    <div class="text-sm font-semibold text-white">
                      System Health
                    </div>
                    <div class="mt-1 text-xs text-slate-400">
                      lensnode_health / lensnode_cleanup / run_retention
                    </div>
                  </div>
                  <StatusBadge
                    :status="systemHealth.length ? 'success' : 'disabled'"
                  />
                </div>
                <div class="mt-4 space-y-3">
                  <div
                    v-for="task in systemHealth"
                    :key="task.task_type"
                    class="rounded-2xl border border-white/10 bg-white/5 p-3"
                  >
                    <div class="flex items-center justify-between gap-3">
                      <div class="text-sm font-medium text-white">
                        {{ task.name }}
                      </div>
                      <StatusBadge :status="task.last_status" />
                    </div>
                    <div class="mt-2 text-xs leading-5 text-slate-400">
                      last run: {{ formatClock(task.last_run_at) }}
                    </div>
                  </div>
                </div>
              </div>

              <div
                class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
              >
                <div class="text-sm font-semibold text-white">
                  DataSources / Skills / MCP
                </div>
                <div class="mt-3 grid gap-2 text-xs text-slate-300">
                  <div
                    class="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-3"
                  >
                    <span>DataSources</span>
                    <span>{{ dataSources.length }}</span>
                  </div>
                  <div
                    class="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-3"
                  >
                    <span>Skills</span>
                    <span>{{ skills.length }}</span>
                  </div>
                  <div
                    class="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-3"
                  >
                    <span>MCP</span>
                    <span>{{ mcps.length }}</span>
                  </div>
                  <div
                    class="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-3"
                  >
                    <span>Global Settings</span>
                    <span>{{ globalSettings.length }}</span>
                  </div>
                </div>
              </div>

              <div
                class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
              >
                <div class="text-sm font-semibold text-white">
                  Current Assistant
                </div>
                <div class="mt-3 space-y-2 text-sm text-slate-300">
                  <div class="flex items-center justify-between gap-3">
                    <span>task</span>
                    <span>{{ selectedAssistant?.selected_task || '-' }}</span>
                  </div>
                  <div class="flex items-center justify-between gap-3">
                    <span>skills</span>
                    <span
                      >{{ selectedAssistant?.skill_summary?.enabled || 0 }}/{{
                        selectedAssistant?.skill_summary?.total || 0
                      }}</span
                    >
                  </div>
                  <div class="flex items-center justify-between gap-3">
                    <span>mcp</span>
                    <span
                      >{{ selectedAssistant?.mcp_summary?.enabled || 0 }}/{{
                        selectedAssistant?.mcp_summary?.total || 0
                      }}</span
                    >
                  </div>
                  <div class="flex items-center justify-between gap-3">
                    <span>dirs</span>
                    <span>{{
                      selectedAssistant?.selected_dirs?.length || 0
                    }}</span>
                  </div>
                </div>
              </div>
            </div>
          </BaseCard>
        </aside>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCard from '@/components/ui/BaseCard.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { useToast } from '@/composables/useToast'
import apiConfig from '@/config/api'

import {
  cancelRun,
  createRun,
  createSession,
  getRun,
  getSystemHealth,
  listAssistants,
  listDataSources,
  listGlobalSettings,
  listMessages,
  listMcpServers,
  listSessions,
  listSkills
} from '@/api/lens'

const route = useRoute()
const router = useRouter()
const { showError, showInfo, showSuccess, showWarning } = useToast()

const scopes = [
  { key: 'assistant', label: 'Assistant', hint: '选择和切换当前助手' },
  { key: 'session', label: 'Session', hint: '深链到具体会话' },
  { key: 'system', label: 'System', hint: '管理员系统快照' }
]

const loading = ref({
  bootstrap: false,
  sessions: false,
  run: false,
  stream: false
})

const assistants = ref([])
const sessions = ref([])
const messages = ref([])
const dataSources = ref([])
const skills = ref([])
const mcps = ref([])
const globalSettings = ref([])
const systemHealth = ref([])
const selectedAssistantUuid = ref('')
const selectedSessionUuid = ref('')
const currentRun = ref(null)
const runEvents = ref([])
const question = ref('请解释为什么同步任务应该归属于数据源管理。')
const runInline = ref(false)
const partialAnswer = ref('')
const finalAnswer = ref('')
const streamError = ref('')
const progress = ref(0)
const activeScope = ref('assistant')
const streamController = ref(null)

const selectedAssistant = computed(
  () =>
    assistants.value.find(
      (item) => item.uuid === selectedAssistantUuid.value
    ) || null
)

const selectedSession = computed(
  () =>
    sessions.value.find((item) => item.uuid === selectedSessionUuid.value) ||
    null
)

const badgeStatus = computed(() => {
  if (!currentRun.value) {
    return 'pending'
  }
  if (currentRun.value.status === 'running') {
    return 'running'
  }
  if (currentRun.value.status === 'queued') {
    return 'running'
  }
  if (currentRun.value.status === 'cancelled') {
    return 'cancelled'
  }
  return currentRun.value.status
})

const runStateLabel = computed(() => {
  if (!currentRun.value) {
    return '等待提交查询'
  }
  if (currentRun.value.status === 'running') {
    return '运行中'
  }
  if (currentRun.value.status === 'queued') {
    return '排队中'
  }
  if (currentRun.value.status === 'failed') {
    return '失败'
  }
  if (currentRun.value.status === 'cancelled') {
    return '已取消'
  }
  return '已完成'
})

const canCancelRun = computed(() =>
  ['queued', 'running', 'streaming'].includes(currentRun.value?.status)
)

const topMetrics = computed(() => [
  {
    label: 'Assistants',
    value: `${assistants.value.length}`,
    help: '真实 API 返回的助手数量'
  },
  {
    label: 'Sessions',
    value: `${sessions.value.length}`,
    help: '当前 assistant 的会话数'
  },
  {
    label: 'Run 状态',
    value: runStateLabel.value,
    help: 'queued / running / failed / done'
  },
  {
    label: '健康面板',
    value: `${systemHealth.value.length}`,
    help: 'lensnode_health / lensnode_cleanup / run_retention'
  }
])

function setLoading(key, value) {
  loading.value = {
    ...loading.value,
    [key]: value
  }
}

function formatClock(iso) {
  if (!iso) {
    return '未记录'
  }
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(iso))
}

function eventDotClass(type) {
  const classes = {
    sync: 'bg-sky-400',
    step: 'bg-cyan-400',
    token: 'bg-emerald-400',
    ping: 'bg-slate-400',
    error: 'bg-rose-400',
    cancelled: 'bg-orange-400',
    status: 'bg-yellow-400',
    done: 'bg-emerald-400'
  }
  return classes[type] || 'bg-slate-400'
}

function pushRunEvent(type, title, detail) {
  runEvents.value = [
    {
      id: `evt-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      type,
      title,
      detail,
      time: new Intl.DateTimeFormat('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      }).format(new Date())
    },
    ...runEvents.value
  ].slice(0, 12)
}

function updateRouteQuery(payload) {
  router.replace({
    query: {
      ...route.query,
      ...payload
    }
  })
}

function buildAuthHeaders() {
  const token = localStorage.getItem('access_token')
  return token
    ? {
        Authorization: `Bearer ${token}`
      }
    : {}
}

async function readSse(runUuid) {
  if (streamController.value) {
    streamController.value.abort()
  }

  const controller = new AbortController()
  streamController.value = controller
  setLoading('stream', true)
  streamError.value = ''

  try {
    const response = await fetch(
      `${apiConfig.apiBaseUrl}/lens/runs/${runUuid}/stream/`,
      {
        headers: {
          Accept: 'text/event-stream',
          ...buildAuthHeaders()
        },
        signal: controller.signal
      }
    )

    if (!response.ok || !response.body) {
      throw new Error(`SSE request failed: ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let reading = true

    while (reading) {
      const { done, value } = await reader.read()
      if (done) {
        reading = false
        continue
      }

      buffer += decoder.decode(value, { stream: true })

      let eventBoundary = buffer.indexOf('\n\n')
      while (eventBoundary !== -1) {
        const rawEvent = buffer.slice(0, eventBoundary)
        buffer = buffer.slice(eventBoundary + 2)
        eventBoundary = buffer.indexOf('\n\n')

        const dataLine = rawEvent
          .split('\n')
          .find((line) => line.startsWith('data: '))

        if (!dataLine) {
          continue
        }

        const payload = JSON.parse(dataLine.slice(6))
        handleStreamEvent(payload)
      }
    }
  } catch (error) {
    if (error.name !== 'AbortError') {
      streamError.value = 'SSE 连接失败'
      showError('SSE 连接失败，请刷新后重试。')
    }
  } finally {
    setLoading('stream', false)
    streamController.value = null
  }
}

function handleStreamEvent(event) {
  if (event.type === 'sync') {
    if (currentRun.value) {
      currentRun.value = {
        ...currentRun.value,
        status: event.status
      }
    }
    if (event.content) {
      if (event.status === 'done') {
        finalAnswer.value = event.content
      } else {
        partialAnswer.value = event.content
      }
    }
    const doneSteps =
      event.steps?.filter((step) => step.status === 'done') || []
    progress.value = Math.max(
      progress.value,
      Math.min(doneSteps.length * 22, 88)
    )
    pushRunEvent('sync', 'Sync', `状态快照：${event.status}`)
    return
  }

  if (event.type === 'step') {
    pushRunEvent('step', `Step: ${event.step}`, JSON.stringify(event.detail))
    progress.value = Math.min(progress.value + 18, 80)
    return
  }

  if (event.type === 'token') {
    if (
      currentRun.value?.status === 'failed' ||
      currentRun.value?.status === 'running'
    ) {
      partialAnswer.value = event.content
    } else {
      finalAnswer.value = event.content
    }
    progress.value = 100
    pushRunEvent('token', 'Token', '收到完整答案片段。')
    return
  }

  if (event.type === 'error') {
    streamError.value = event.error || '运行失败'
    pushRunEvent('error', 'Run failed', event.error || '运行失败')
    progress.value = 100
    return
  }

  if (event.type === 'cancelled') {
    pushRunEvent('cancelled', 'Run cancelled', '运行被手动中止。')
    progress.value = 100
    return
  }

  if (event.type === 'status') {
    if (currentRun.value) {
      currentRun.value = {
        ...currentRun.value,
        status: event.status
      }
    }
    pushRunEvent('status', `Status: ${event.status}`, '运行中。')
    return
  }

  if (event.type === 'ping') {
    pushRunEvent('ping', 'Ping', '后端仍在处理。')
    return
  }

  if (event.type === 'done') {
    pushRunEvent('done', 'Run done', '查询已完成。')
    progress.value = 100
  }
}

async function loadSessionsAndMessages(selectUuid = '') {
  if (!selectedAssistantUuid.value) {
    sessions.value = []
    messages.value = []
    currentRun.value = null
    return
  }

  setLoading('sessions', true)
  try {
    sessions.value = await listSessions(selectedAssistant.value?.slug || '')

    let sessionUuid =
      selectUuid ||
      selectedSessionUuid.value ||
      route.query.session ||
      sessions.value[0]?.uuid ||
      ''

    if (!sessions.value.length) {
      const created = await createStarterSession(false)
      if (created) {
        sessionUuid = created.uuid
      }
    }

    if (!sessionUuid) {
      selectedSessionUuid.value = ''
      messages.value = []
      currentRun.value = null
      return
    }

    selectedSessionUuid.value = sessionUuid
    updateRouteQuery({
      assistant: selectedAssistant.value?.slug || '',
      session: sessionUuid
    })

    messages.value = await listMessages(sessionUuid)
    partialAnswer.value = ''
    finalAnswer.value = ''
    streamError.value = ''
    const runUuid = [...messages.value]
      .reverse()
      .map((message) => message.run)
      .find(Boolean)
    const assistantMessage = [...messages.value]
      .reverse()
      .find(
        (message) => message.run === runUuid && message.role === 'assistant'
      )

    if (runUuid) {
      currentRun.value = await getRun(runUuid)
      finalAnswer.value =
        currentRun.value?.status === 'done'
          ? assistantMessage?.content || ''
          : ''
      partialAnswer.value =
        currentRun.value?.status === 'failed' ||
        currentRun.value?.status === 'cancelled' ||
        currentRun.value?.status === 'queued' ||
        currentRun.value?.status === 'running'
          ? assistantMessage?.content || ''
          : partialAnswer.value
    } else {
      currentRun.value = null
      finalAnswer.value = ''
    }
  } finally {
    setLoading('sessions', false)
  }
}

async function bootstrap() {
  setLoading('bootstrap', true)
  try {
    const assistantList = await listAssistants()

    assistants.value = assistantList

    const [sourceList, skillList, mcpList, settingList, healthList] =
      await Promise.allSettled([
        listDataSources(),
        listSkills(),
        listMcpServers(),
        listGlobalSettings(),
        getSystemHealth()
      ])

    dataSources.value =
      sourceList.status === 'fulfilled' ? sourceList.value : []
    skills.value = skillList.status === 'fulfilled' ? skillList.value : []
    mcps.value = mcpList.status === 'fulfilled' ? mcpList.value : []
    globalSettings.value =
      settingList.status === 'fulfilled' ? settingList.value : []
    systemHealth.value =
      healthList.status === 'fulfilled' ? healthList.value : []

    const assistantSlug = route.query.assistant
    const assistant =
      assistantList.find((item) => item.slug === assistantSlug) ||
      assistantList[0] ||
      null

    if (assistant) {
      selectedAssistantUuid.value = assistant.uuid
      updateRouteQuery({ assistant: assistant.slug })
      await loadSessionsAndMessages(route.query.session || '')
    } else {
      sessions.value = []
      messages.value = []
      currentRun.value = null
    }
  } catch (error) {
    showError('Lens API 加载失败，请先确认后端迁移与权限。')
  } finally {
    setLoading('bootstrap', false)
  }
}

async function createStarterSession(shouldNotify = true) {
  if (!selectedAssistant.value) {
    return null
  }

  const created = await createSession({
    assistant_uuid: selectedAssistant.value.uuid,
    title: 'AI Query Demo'
  })

  sessions.value = [created, ...sessions.value]
  selectedSessionUuid.value = created.uuid
  updateRouteQuery({
    assistant: selectedAssistant.value.slug,
    session: created.uuid
  })

  if (shouldNotify) {
    showSuccess('已创建新会话。')
    await loadSessionsAndMessages(created.uuid)
  } else {
    messages.value = []
    currentRun.value = null
  }
  return created
}

async function selectAssistant(assistant) {
  selectedAssistantUuid.value = assistant.uuid
  updateRouteQuery({ assistant: assistant.slug, session: null })
  await loadSessionsAndMessages('')
}

async function handleAssistantChange() {
  const assistant = selectedAssistant.value
  if (!assistant) {
    return
  }
  await selectAssistant(assistant)
}

async function selectSession(session) {
  selectedSessionUuid.value = session.uuid
  updateRouteQuery({
    assistant: selectedAssistant.value?.slug || '',
    session: session.uuid
  })
  await loadSessionsAndMessages(session.uuid)
}

async function refreshSession() {
  if (!selectedSessionUuid.value) {
    return
  }
  await loadSessionsAndMessages(selectedSessionUuid.value)
}

async function startQuery() {
  if (!selectedSession.value) {
    showWarning('请先选择或创建会话。')
    return
  }

  setLoading('run', true)
  partialAnswer.value = ''
  finalAnswer.value = ''
  streamError.value = ''
  runEvents.value = []
  progress.value = 6

  try {
    const created = await createRun(selectedSession.value.uuid, {
      question: question.value,
      run_inline: runInline.value,
      enqueue: !runInline.value
    })

    currentRun.value = created
    await loadSessionsAndMessages(selectedSession.value.uuid)
    currentRun.value = created

    if (created.uuid) {
      await readSse(created.uuid)
      const refreshed = await getRun(created.uuid)
      currentRun.value = refreshed
      const assistantMessage = messages.value
        .slice()
        .reverse()
        .find(
          (message) =>
            message.run === refreshed.uuid && message.role === 'assistant'
        )
      partialAnswer.value =
        refreshed.status === 'failed'
          ? assistantMessage?.content || '已生成部分答案，但最终整理失败。'
          : partialAnswer.value || ''
      finalAnswer.value =
        refreshed.status === 'done'
          ? assistantMessage?.content || finalAnswer.value
          : ''
      if (refreshed.status === 'failed') {
        streamError.value = refreshed.error || streamError.value
      }
      progress.value = ['queued', 'running', 'streaming'].includes(
        refreshed.status
      )
        ? Math.max(progress.value, 60)
        : 100
    }

    showInfo('查询请求已提交。')
  } catch (error) {
    showError('创建 Run 失败，请检查后端接口。')
  } finally {
    setLoading('run', false)
  }
}

async function cancelCurrentRun() {
  if (
    !currentRun.value ||
    !['queued', 'running', 'streaming'].includes(currentRun.value.status)
  ) {
    return
  }

  if (streamController.value) {
    streamController.value.abort()
  }

  const response = await cancelRun(currentRun.value.uuid)
  currentRun.value = response
  await refreshSession()
  showWarning('当前 Run 已取消。')
}

function resetQuery() {
  question.value = '请解释为什么同步任务应该归属于数据源管理。'
  runInline.value = false
  runEvents.value = []
  partialAnswer.value = ''
  finalAnswer.value = ''
  streamError.value = ''
  progress.value = 0
}

watch(
  () => route.query.assistant,
  (value) => {
    if (!value || !assistants.value.length) {
      return
    }
    const assistant = assistants.value.find((item) => item.slug === value)
    if (assistant && assistant.uuid !== selectedAssistantUuid.value) {
      selectedAssistantUuid.value = assistant.uuid
      loadSessionsAndMessages(route.query.session || '')
    }
  }
)

watch(
  () => route.query.session,
  (value) => {
    if (!value || !sessions.value.length) {
      return
    }
    if (value !== selectedSessionUuid.value) {
      selectedSessionUuid.value = value
      loadSessionsAndMessages(value)
    }
  }
)

onMounted(() => {
  bootstrap()
})
</script>
