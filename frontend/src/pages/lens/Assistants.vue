<template>
  <AppLayout>
    <div class="mx-auto flex max-w-7xl flex-col gap-5">
      <header class="rounded-lg border border-gray-200 bg-white px-5 py-4">
        <div
          class="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between"
        >
          <div>
            <p class="text-xs font-semibold uppercase text-gray-500">Lens</p>
            <h1 class="mt-1 text-2xl font-semibold text-gray-900">
              Assistants
            </h1>
            <p class="mt-2 max-w-3xl text-sm leading-6 text-gray-600">
              面向 LensNode 工作区目录的助手入口，展示任务、目录和模型引用检查。
            </p>
          </div>
          <BaseButton :loading="loading" variant="secondary" @click="load">
            刷新
          </BaseButton>
        </div>
      </header>

      <section class="grid gap-4 md:grid-cols-4">
        <div
          v-for="metric in metrics"
          :key="metric.label"
          class="rounded-lg border border-gray-200 bg-white p-4"
        >
          <div class="text-xs font-medium text-gray-500">
            {{ metric.label }}
          </div>
          <div class="mt-2 text-2xl font-semibold text-gray-900">
            {{ metric.value }}
          </div>
        </div>
      </section>

      <section class="rounded-lg border border-gray-200 bg-white">
        <div class="border-b border-gray-200 px-5 py-4">
          <h2 class="text-base font-semibold text-gray-900">助手目录</h2>
        </div>

        <div v-if="assistants.length" class="divide-y divide-gray-100">
          <article
            v-for="assistant in assistants"
            :key="assistant.uuid"
            class="grid gap-4 px-5 py-4 lg:grid-cols-[1fr_220px_220px]"
          >
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="truncate text-base font-semibold text-gray-900">
                  {{ assistant.name }}
                </h3>
                <StatusBadge :status="assistant.status" />
                <StatusBadge :status="modelCheckStatus(assistant)" />
              </div>
              <p class="mt-1 text-sm text-gray-500">
                {{ assistant.slug }} · {{ assistant.selected_task || '-' }}
              </p>
              <div class="mt-3 flex flex-wrap gap-2 text-xs text-gray-500">
                <span class="rounded-md bg-gray-100 px-2 py-1">
                  LensNode {{ compactUuid(assistant.lensnode) }}
                </span>
                <span class="rounded-md bg-gray-100 px-2 py-1">
                  Dirs {{ assistant.selected_dirs?.length || 0 }}
                </span>
                <span class="rounded-md bg-gray-100 px-2 py-1">
                  Skills {{ assistant.skill_summary?.enabled || 0 }}/{{
                    assistant.skill_summary?.total || 0
                  }}
                </span>
                <span class="rounded-md bg-gray-100 px-2 py-1">
                  MCP {{ assistant.mcp_summary?.enabled || 0 }}/{{
                    assistant.mcp_summary?.total || 0
                  }}
                </span>
              </div>
            </div>

            <div class="text-sm text-gray-600">
              <div class="font-medium text-gray-900">模型检查</div>
              <div class="mt-2 space-y-1">
                <div
                  v-for="field in modelFields"
                  :key="field"
                  class="flex justify-between gap-3"
                >
                  <span>{{ fieldLabels[field] }}</span>
                  <span>
                    {{
                      assistant.settings?._model_check?.[field]?.status || '-'
                    }}
                  </span>
                </div>
              </div>
            </div>

            <div class="flex items-start justify-end gap-2">
              <BaseButton
                variant="primary"
                size="sm"
                @click="goChat(assistant)"
              >
                进入查询
              </BaseButton>
              <BaseButton
                variant="secondary"
                size="sm"
                @click="goHistory(assistant)"
              >
                历史
              </BaseButton>
            </div>
          </article>
        </div>

        <div v-else class="px-5 py-16 text-center">
          <div class="text-sm font-medium text-gray-900">暂无助手</div>
          <p class="mt-2 text-sm text-gray-500">
            后端创建 Assistant 后会显示在这里。
          </p>
        </div>
      </section>
    </div>
  </AppLayout>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'

import AppLayout from '@/components/layout/AppLayout.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { useToast } from '@/composables/useToast'
import { useLensStore } from '@/store/lens'

import { compactUuid, modelCheckStatus } from './format'

const router = useRouter()
const { showError } = useToast()
const lensStore = useLensStore()
const { assistants, loading } = storeToRefs(lensStore)
const modelFields = [
  'preprocess_model_ref',
  'postprocess_model_ref',
  'agent_model_ref',
  'multimodal_model_ref'
]
const fieldLabels = {
  preprocess_model_ref: 'Pre',
  postprocess_model_ref: 'Post',
  agent_model_ref: 'Agent',
  multimodal_model_ref: 'Multi'
}

const metrics = computed(() => {
  const active = assistants.value.filter((item) => item.status === 'active')
  const checked = assistants.value.filter(
    (item) => modelCheckStatus(item) === 'success'
  )
  return [
    { label: '全部助手', value: assistants.value.length },
    { label: '启用中', value: active.length },
    { label: '模型通过', value: checked.length },
    {
      label: '目录选择',
      value: assistants.value.reduce(
        (total, item) => total + (item.selected_dirs?.length || 0),
        0
      )
    }
  ]
})

async function load() {
  try {
    await lensStore.loadAssistants()
  } catch {
    showError('加载 Lens assistants 失败。')
  }
}

function goChat(assistant) {
  router.push(`/lens/assistants/${assistant.slug}/chat`)
}

function goHistory(assistant) {
  router.push(`/lens/assistants/${assistant.slug}/history`)
}

onMounted(load)
</script>
