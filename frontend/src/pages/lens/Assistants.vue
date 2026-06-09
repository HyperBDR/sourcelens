<template>
  <AppLayout>
    <div class="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-4 lg:px-6">
      <section class="rounded-lg border border-line bg-surface shadow-sm">
        <div
          class="flex flex-col gap-4 border-b border-line px-5 py-4 lg:flex-row lg:items-end lg:justify-between"
        >
          <div class="min-w-0">
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-lg font-semibold text-ink-900">Assistants</h1>
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1 text-xs font-medium text-ink-500"
              >
                Lens
              </span>
            </div>
            <p class="mt-1 max-w-3xl text-sm leading-6 text-ink-500">
              面向 LensNode 工作区目录的助手入口，统一展示状态、目录和工具配置。
            </p>
          </div>
          <BaseButton :loading="loading" variant="outline" @click="load">
            {{ t('common.refresh') }}
          </BaseButton>
        </div>

        <div class="grid gap-3 border-b border-line bg-surface-sunken px-5 py-4 sm:grid-cols-2 xl:grid-cols-4">
          <div
            v-for="metric in metrics"
            :key="metric.label"
            class="rounded-lg border border-line bg-surface px-4 py-3"
          >
            <div class="text-xs font-medium text-ink-500">
              {{ metric.label }}
            </div>
            <div class="mt-2 text-2xl font-semibold text-ink-900">
              {{ metric.value }}
            </div>
          </div>
        </div>

        <div class="px-5 py-4">
          <BaseLoading v-if="loading && !assistants.length" />

          <div
            v-else-if="!assistants.length"
            class="rounded-lg border border-line bg-surface-sunken py-16 text-center"
          >
            <div class="text-sm font-medium text-ink-900">暂无助手</div>
            <p class="mt-2 text-sm text-ink-500">
              后端创建 Assistant 后会显示在这里。
            </p>
          </div>

          <div
            v-else
            class="overflow-x-auto rounded-lg border border-line bg-surface"
          >
            <table class="min-w-full divide-y divide-line">
              <thead class="bg-surface-sunken">
                <tr>
                  <th class="table-head">Assistant</th>
                  <th class="table-head">LensNode</th>
                  <th class="table-head">Task</th>
                  <th class="table-head">Dirs</th>
                  <th class="table-head">Tools</th>
                  <th class="table-head">Status</th>
                  <th class="table-head text-right">Actions</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line bg-surface">
                <tr
                  v-for="assistant in assistants"
                  :key="assistant.uuid"
                  class="transition-colors hover:bg-surface-sunken"
                >
                  <td class="table-cell">
                    <div class="font-medium text-ink-900">
                      {{ assistant.name }}
                    </div>
                    <div class="mt-1 text-xs text-ink-500">
                      {{ assistant.slug }}
                    </div>
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ lensNodeName(assistant.lensnode) }}
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ assistant.selected_task || '-' }}
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ assistant.selected_dirs?.length || 0 }}
                  </td>
                  <td class="table-cell text-ink-600">
                    <div class="space-y-1">
                      <div>
                        Skills {{ assistant.skill_summary?.enabled || 0 }}/{{
                          assistant.skill_summary?.total || 0
                        }}
                      </div>
                      <div>
                        MCP {{ assistant.mcp_summary?.enabled || 0 }}/{{
                          assistant.mcp_summary?.total || 0
                        }}
                      </div>
                    </div>
                  </td>
                  <td class="table-cell">
                    <div class="flex flex-wrap gap-2">
                      <StatusBadge :status="assistant.status" />
                      <StatusBadge :status="modelCheckStatus(assistant)" />
                    </div>
                  </td>
                  <td class="table-cell">
                    <div class="flex justify-end gap-2">
                      <BaseButton
                        variant="primary"
                        size="sm"
                        @click="goChat(assistant)"
                      >
                        进入查询
                      </BaseButton>
                      <BaseButton
                        variant="outline"
                        size="sm"
                        @click="goHistory(assistant)"
                      >
                        历史
                      </BaseButton>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  </AppLayout>
</template>

<script setup>
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useI18n } from 'vue-i18n'

import AppLayout from '@/components/layout/AppLayout.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { useToast } from '@/composables/useToast'
import { useLensStore } from '@/store/lens'

import { compactUuid, modelCheckStatus } from './format'

const router = useRouter()
const { t } = useI18n()
const { showError } = useToast()
const lensStore = useLensStore()
const { assistants, loading } = storeToRefs(lensStore)

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

function lensNodeName(value) {
  if (!value) return '-'
  if (typeof value === 'object') {
    return value.name || value.uuid || '-'
  }
  return compactUuid(value)
}

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

<style scoped>
.table-head {
  @apply border-b border-line px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-500;
}

.table-cell {
  @apply px-4 py-4 text-sm text-ink-700;
}
</style>
