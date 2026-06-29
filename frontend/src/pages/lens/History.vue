<template>
  <AppLayout>
    <div
      class="mx-auto grid h-[calc(100vh-5.5rem)] max-w-7xl gap-5 px-4 py-4 lg:grid-cols-[320px_1fr] lg:px-6"
    >
      <aside
        class="flex min-h-0 flex-col overflow-hidden rounded-lg border border-line bg-surface shadow-sm"
      >
        <div class="flex-shrink-0 border-b border-line px-4 py-3">
          <h1 class="text-base font-semibold text-ink-900">History</h1>
          <p class="mt-1 text-sm text-ink-500">
            {{ assistant?.name || route.params.slug }}
          </p>
        </div>
        <div class="min-h-0 flex-1 divide-y divide-line overflow-y-auto">
          <button
            v-for="session in pagedSessions"
            :key="session.uuid"
            class="w-full px-4 py-3 text-left transition-colors hover:bg-surface-sunken"
            :class="selectedSessionUuid === session.uuid ? 'bg-brand-50' : ''"
            @click="selectSession(session)"
          >
            <div class="truncate text-sm font-medium text-ink-900">
              {{ session.title || '未命名会话' }}
            </div>
            <div class="mt-1 text-xs text-ink-500">
              {{ formatDateTime(session.created_at) }}
            </div>
          </button>
        </div>
        <div
          v-if="sessionTotal > 0"
          class="flex flex-shrink-0 flex-col gap-3 border-t border-line px-4 py-3"
        >
          <div class="text-sm font-medium text-ink-700">
            {{ t('common.pagination.showing', sessionPaginationShowing) }}
          </div>
          <div class="flex flex-wrap items-center gap-3">
            <label class="text-sm text-ink-500">
              {{ t('common.pagination.itemsPerPage') }}:
            </label>
            <select
              v-model.number="sessionPageSize"
              class="rounded-md border border-line bg-surface px-2 py-1.5 text-sm focus:border-brand-500 focus:outline-none focus:ring-1 focus:ring-brand-500"
              @change="handleSessionPageSizeChange"
            >
              <option :value="10">10</option>
              <option :value="20">20</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
            </select>
            <BaseButton
              variant="outline"
              size="sm"
              :disabled="sessionPage <= 1"
              :title="t('common.pagination.previous')"
              @click="goPrevSessionPage"
            >
              <svg
                class="h-4 w-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M15 19l-7-7 7-7"
                />
              </svg>
              <span class="sr-only">
                {{ t('common.pagination.previous') }}
              </span>
            </BaseButton>
            <span
              class="rounded-md border border-line bg-surface-sunken px-3 py-1.5 text-sm font-semibold text-ink-700"
            >
              {{
                t('common.pagination.page', {
                  current: sessionPage,
                  total: sessionTotalPages
                })
              }}
            </span>
            <BaseButton
              variant="outline"
              size="sm"
              :disabled="sessionPage >= sessionTotalPages"
              :title="t('common.pagination.next')"
              @click="goNextSessionPage"
            >
              <svg
                class="h-4 w-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M9 5l7 7-7 7"
                />
              </svg>
              <span class="sr-only">{{ t('common.pagination.next') }}</span>
            </BaseButton>
          </div>
        </div>
      </aside>

      <main
        class="flex min-h-0 flex-col overflow-hidden rounded-lg border border-line bg-surface shadow-sm"
      >
        <div
          class="flex flex-shrink-0 items-center justify-between gap-3 border-b border-line px-5 py-4"
        >
          <div>
            <h2 class="text-lg font-semibold text-ink-900">消息记录</h2>
            <p class="mt-1 text-sm text-ink-500">
              仅展示当前会话的消息，不混入运行调试信息。
            </p>
          </div>
          <BaseButton variant="outline" size="sm" @click="load">
            刷新
          </BaseButton>
        </div>

        <div class="min-h-0 flex-1 bg-surface-sunken p-5">
          <div
            v-if="messages.length"
            class="max-h-full space-y-3 overflow-y-auto"
          >
            <article
              v-for="message in messages"
              :key="message.uuid"
              class="rounded-lg border border-line bg-surface px-4 py-3"
            >
              <div class="flex items-center justify-between gap-3">
                <div
                  class="text-xs font-semibold uppercase tracking-wide text-ink-500"
                >
                  {{ message.role }}
                </div>
                <div class="text-xs text-ink-400">#{{ message.sequence }}</div>
              </div>
              <div
                class="mt-2 whitespace-pre-wrap text-sm leading-6 text-ink-700"
              >
                {{ message.content || '（空）' }}
              </div>
              <div v-if="message.run" class="mt-3 text-xs text-ink-400">
                run {{ compactUuid(message.run) }}
              </div>
            </article>
          </div>

          <div
            v-if="!messages.length"
            class="rounded-lg border border-line bg-surface py-16 text-center"
          >
            <div class="text-sm font-medium text-ink-900">暂无消息</div>
          </div>
        </div>
      </main>
    </div>
  </AppLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'

import AppLayout from '@/components/layout/AppLayout.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import { useToast } from '@/composables/useToast'
import { listAssistants, listMessages, listSessions } from '@/api/lens'

import { compactUuid, formatDateTime } from './format'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { showError } = useToast()
const assistant = ref(null)
const sessions = ref([])
const messages = ref([])
const selectedSessionUuid = ref('')
const sessionPage = ref(1)
const sessionPageSize = ref(20)

const sessionTotal = computed(() => sessions.value.length)
const sessionTotalPages = computed(() =>
  Math.max(1, Math.ceil(sessionTotal.value / sessionPageSize.value))
)
const pagedSessions = computed(() => {
  const start = (sessionPage.value - 1) * sessionPageSize.value
  return sessions.value.slice(start, start + sessionPageSize.value)
})
const sessionPaginationShowing = computed(() => ({
  from: (sessionPage.value - 1) * sessionPageSize.value + 1,
  to: Math.min(sessionPage.value * sessionPageSize.value, sessionTotal.value),
  total: sessionTotal.value
}))

async function load() {
  try {
    const assistants = await listAssistants()
    assistant.value = assistants.find((item) => item.slug === route.params.slug)
    sessions.value = await listSessions(route.params.slug)
    const target = route.query.session || sessions.value[0]?.uuid
    if (target) {
      moveToSessionPage(target)
      await selectSession({ uuid: target }, false)
    }
  } catch {
    showError('加载历史记录失败。')
  }
}

async function selectSession(session, updateRoute = true) {
  selectedSessionUuid.value = session.uuid
  messages.value = await listMessages(session.uuid)
  if (updateRoute) {
    router.replace({ query: { session: session.uuid } })
  }
}

function moveToSessionPage(sessionUuid) {
  const index = sessions.value.findIndex((item) => item.uuid === sessionUuid)
  if (index >= 0) {
    sessionPage.value = Math.floor(index / sessionPageSize.value) + 1
  }
}

function handleSessionPageSizeChange() {
  const selected = selectedSessionUuid.value
  if (selected) {
    moveToSessionPage(selected)
    return
  }
  sessionPage.value = 1
}

function goPrevSessionPage() {
  if (sessionPage.value <= 1) return
  sessionPage.value -= 1
}

function goNextSessionPage() {
  if (sessionPage.value >= sessionTotalPages.value) return
  sessionPage.value += 1
}

onMounted(load)
</script>
