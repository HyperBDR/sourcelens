<template>
  <AppLayout>
    <div class="mx-auto grid max-w-7xl gap-5 px-4 py-4 lg:grid-cols-[320px_1fr] lg:px-6">
      <aside class="rounded-lg border border-line bg-surface shadow-sm">
        <div class="border-b border-line px-4 py-3">
          <h1 class="text-base font-semibold text-ink-900">History</h1>
          <p class="mt-1 text-sm text-ink-500">
            {{ assistant?.name || route.params.slug }}
          </p>
        </div>
        <div class="max-h-[calc(100vh-11rem)] divide-y divide-line overflow-y-auto">
          <button
            v-for="session in sessions"
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
      </aside>

      <main class="rounded-lg border border-line bg-surface shadow-sm">
        <div class="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
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

        <div class="space-y-3 bg-surface-sunken p-5">
          <article
            v-for="message in messages"
            :key="message.uuid"
            class="rounded-lg border border-line bg-surface px-4 py-3"
          >
            <div class="flex items-center justify-between gap-3">
              <div class="text-xs font-semibold uppercase tracking-wide text-ink-500">
                {{ message.role }}
              </div>
              <div class="text-xs text-ink-400">#{{ message.sequence }}</div>
            </div>
            <div class="mt-2 whitespace-pre-wrap text-sm leading-6 text-ink-700">
              {{ message.content || '（空）' }}
            </div>
            <div v-if="message.run" class="mt-3 text-xs text-ink-400">
              run {{ compactUuid(message.run) }}
            </div>
          </article>

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
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import AppLayout from '@/components/layout/AppLayout.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import { useToast } from '@/composables/useToast'
import { listAssistants, listMessages, listSessions } from '@/api/lens'

import { compactUuid, formatDateTime } from './format'

const route = useRoute()
const router = useRouter()
const { showError } = useToast()
const assistant = ref(null)
const sessions = ref([])
const messages = ref([])
const selectedSessionUuid = ref('')

async function load() {
  try {
    const assistants = await listAssistants()
    assistant.value = assistants.find((item) => item.slug === route.params.slug)
    sessions.value = await listSessions(route.params.slug)
    const target = route.query.session || sessions.value[0]?.uuid
    if (target) {
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

onMounted(load)
</script>
