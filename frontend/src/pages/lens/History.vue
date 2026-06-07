<template>
  <AppLayout>
    <div class="mx-auto grid max-w-7xl gap-5 lg:grid-cols-[340px_1fr]">
      <aside class="rounded-lg border border-gray-200 bg-white">
        <div class="border-b border-gray-200 px-4 py-3">
          <h1 class="text-base font-semibold text-gray-900">History</h1>
          <p class="mt-1 text-sm text-gray-500">
            {{ assistant?.name || route.params.slug }}
          </p>
        </div>
        <div class="divide-y divide-gray-100">
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
      </aside>

      <main class="rounded-lg border border-gray-200 bg-white">
        <div class="border-b border-gray-200 px-5 py-4">
          <div class="flex items-center justify-between gap-3">
            <h2 class="text-lg font-semibold text-gray-900">消息记录</h2>
            <BaseButton variant="secondary" size="sm" @click="load">
              刷新
            </BaseButton>
          </div>
        </div>
        <div class="space-y-3 bg-gray-50 p-5">
          <article
            v-for="message in messages"
            :key="message.uuid"
            class="rounded-lg border border-gray-200 bg-white px-4 py-3"
          >
            <div class="flex items-center justify-between gap-3">
              <div class="text-xs font-semibold uppercase text-gray-500">
                {{ message.role }}
              </div>
              <div class="text-xs text-gray-500">#{{ message.sequence }}</div>
            </div>
            <div
              class="mt-2 whitespace-pre-wrap text-sm leading-6 text-gray-800"
            >
              {{ message.content || '（空）' }}
            </div>
            <div v-if="message.run" class="mt-3 text-xs text-gray-500">
              run {{ compactUuid(message.run) }}
            </div>
          </article>

          <div v-if="!messages.length" class="py-16 text-center">
            <div class="text-sm font-medium text-gray-900">暂无消息</div>
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
