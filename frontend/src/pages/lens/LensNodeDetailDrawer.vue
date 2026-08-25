<template>
  <BaseDrawer
    :show="show"
    :title="t('lensAdmin.detail.title')"
    :subtitle="node?.name || ''"
    @close="$emit('close')"
  >
    <div v-if="node" class="space-y-6">
      <!-- Header: id + runtime status -->
      <div class="flex items-center justify-between">
        <span class="font-mono text-xs text-ink-400">
          {{ compactUuid(node.uuid) }}
        </span>
        <StatusBadge :status="node.status" />
      </div>

      <section class="space-y-3">
        <div class="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <div
            v-for="item in nodeMetricCards"
            :key="item.label"
            class="rounded-lg border border-line bg-surface-sunken px-3 py-2.5"
          >
            <div class="text-xs text-ink-500">{{ item.label }}</div>
            <div class="mt-1 text-lg font-semibold tabular-nums text-ink-900">
              {{ item.value }}
            </div>
          </div>
        </div>
        <div class="space-y-3">
          <div class="rounded-lg border border-line bg-surface px-4 py-3">
            <div class="flex items-center justify-between gap-3">
              <span class="text-xs font-medium text-ink-500">
                {{ nodeInfoRows[0].label }}
              </span>
              <span class="text-[11px] text-ink-400">
                {{ t('lensAdmin.detail.runtimeLocation') }}
              </span>
            </div>
            <div class="mt-2 break-all font-mono text-sm text-ink-900">
              {{ nodeInfoRows[0].value }}
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div
              v-for="item in nodeInfoRows.slice(1)"
              :key="item.label"
              class="rounded-lg border border-line bg-surface px-3 py-3"
            >
              <div class="text-xs text-ink-500">{{ item.label }}</div>
              <div class="mt-1.5 break-words text-sm font-medium text-ink-800">
                {{ item.value }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Directory preview (lazy tree) -->
      <div>
        <div class="mb-1.5 text-sm font-medium text-ink-700">
          {{ t('lensAdmin.detail.directoryTree') }}
        </div>
        <p class="mb-2 text-xs text-ink-500">
          {{ t('lensAdmin.detail.treeHint') }}
        </p>
        <div
          v-if="isOffline"
          class="mb-2 rounded-md border border-warning-200 bg-warning-50 px-3 py-2 text-xs text-warning-700"
        >
          {{ t('lensAdmin.detail.offlineHint') }}
        </div>
        <div class="rounded-md border border-line bg-surface-sunken p-2">
          <LensNodeDirTree
            v-if="rootNodes.length"
            :nodes="rootNodes"
            :loader="loadChildren"
          />
          <p v-else class="px-1.5 py-3 text-center text-xs text-ink-400">
            {{ t('lensAdmin.detail.treeEmpty') }}
          </p>
        </div>
      </div>
    </div>
  </BaseDrawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { scanLensNodeDirs } from '@/api/lens'
import { formatOperationMetric } from '@/admin/utils/operationsSummary'
import { useToast } from '@/composables/useToast'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'

import LensNodeDirTree from './LensNodeDirTree.vue'
import { compactUuid } from './adminHelpers'
import { useShortDateTime } from './useShortDateTime'

const props = defineProps({
  show: Boolean,
  node: {
    type: Object,
    default: null
  }
})

defineEmits(['close'])

const { t } = useI18n()
const { showError } = useToast()

const rootNodes = ref([])
const formatDateTime = useShortDateTime()

const isOffline = computed(() => props.node?.status !== 'online')

const nodeMetricCards = computed(() => {
  const node = props.node || {}
  return [
    {
      label: t('lensAdmin.detail.totalRuns'),
      value: formatOperationMetric(node.total_run_count)
    },
    {
      label: t('lensAdmin.detail.succeededRuns'),
      value: formatOperationMetric(node.succeeded_run_count)
    },
    {
      label: t('lensAdmin.detail.failedRuns'),
      value: formatOperationMetric(node.failed_run_count)
    },
    {
      label: t('lensAdmin.detail.totalTokens'),
      value: formatOperationMetric(node.total_tokens)
    },
    {
      label: t('lensAdmin.detail.activeRuns'),
      value: formatOperationMetric(node.active_run_count)
    },
    {
      label: t('lensAdmin.detail.queuedRuns'),
      value: formatOperationMetric(node.queued_run_count)
    }
  ]
})

const nodeInfoRows = computed(() => {
  const node = props.node || {}
  return [
    {
      label: t('lensAdmin.detail.workspace'),
      value: node.workspace_path || t('lensAdmin.detail.notReported')
    },
    {
      label: t('lensAdmin.detail.agentVersion'),
      value: node.agent_version || t('lensAdmin.detail.notReported')
    },
    {
      label: t('lensAdmin.detail.protocolVersion'),
      value: node.protocol_version || t('lensAdmin.detail.notReported')
    },
    {
      label: t('lensAdmin.detail.lastHeartbeat'),
      value: formatDateTime(node.last_heartbeat_at)
    },
    {
      label: t('lensAdmin.detail.lastRun'),
      value: formatDateTime(node.last_run_at)
    }
  ]
})

function toChildNode(child) {
  const path = typeof child === 'string' ? child : child.path
  const name =
    typeof child === 'string'
      ? child.split('/').filter(Boolean).pop() || child
      : child.name || child.path
  return { path, name, children: null, expanded: false, loading: false }
}

function toTopNode(dir) {
  if (typeof dir === 'string') {
    return toChildNode(dir)
  }
  const children = Array.isArray(dir.children)
    ? dir.children.map(toChildNode)
    : null
  return {
    path: dir.path,
    name: dir.name || dir.path,
    children,
    expanded: false,
    loading: false
  }
}

function buildTree() {
  const dirs = Array.isArray(props.node?.available_dirs)
    ? props.node.available_dirs
    : []
  rootNodes.value = dirs.map(toTopNode)
}

async function loadChildren(path) {
  try {
    const result = await scanLensNodeDirs(props.node.uuid, [path])
    const list = result?.dirs?.[path] || []
    return list.map(toChildNode)
  } catch (error) {
    showError(t('lensAdmin.detail.loadDirsFailed'))
    return null
  }
}

watch(
  () => props.show,
  (show) => {
    if (show) {
      buildTree()
    }
  }
)
</script>
