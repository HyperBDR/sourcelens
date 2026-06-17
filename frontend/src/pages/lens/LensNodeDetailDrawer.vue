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

      <!-- Enrollment progress timeline -->
      <div>
        <div class="mb-3 text-sm font-medium text-ink-700">
          {{ t('lensAdmin.timeline.title') }}
        </div>
        <ol class="relative">
          <li
            v-for="(step, i) in timelineSteps"
            :key="step.key"
            class="flex gap-3"
          >
            <div class="flex flex-col items-center">
              <span
                class="mt-1 h-3 w-3 flex-shrink-0 rounded-full"
                :class="dotClass(step.tone)"
              />
              <span
                v-if="i < timelineSteps.length - 1"
                class="my-1 w-px flex-1 bg-line"
              />
            </div>
            <div class="flex-1 pb-4">
              <div class="text-sm font-medium text-ink-800">
                {{ step.label }}
              </div>
              <div
                v-if="step.meta"
                class="text-xs"
                :class="metaClass(step.tone)"
              >
                {{ step.meta }}
              </div>
            </div>
          </li>
        </ol>
      </div>

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

const timelineSteps = computed(() => {
  const node = props.node
  if (!node) return []
  const enrollment = node.enrollment_status
  return [
    {
      key: 'created',
      label: t('lensAdmin.timeline.created'),
      tone: 'done',
      meta: formatDateTime(node.created_at)
    },
    {
      key: 'approved',
      label: t('lensAdmin.timeline.approved'),
      tone:
        enrollment === 'approved'
          ? 'done'
          : enrollment === 'rejected'
            ? 'error'
            : 'pending',
      meta:
        enrollment === 'rejected'
          ? t('lensAdmin.timeline.rejected')
          : enrollment === 'approved'
            ? ''
            : t('lensAdmin.timeline.pendingMeta')
    },
    {
      key: 'credential',
      label: t('lensAdmin.timeline.credential'),
      tone: node.token_revoked ? 'error' : node.has_token ? 'done' : 'pending',
      meta: node.token_revoked
        ? t('lensAdmin.detail.revoked')
        : node.has_token
          ? node.token_issued_at
            ? formatDateTime(node.token_issued_at)
            : t('lensAdmin.detail.active')
          : t('lensAdmin.detail.notIssued')
    },
    {
      key: 'connected',
      label: t('lensAdmin.timeline.connected'),
      tone: node.last_authenticated_at ? 'done' : 'idle',
      meta: node.last_authenticated_at
        ? formatDateTime(node.last_authenticated_at)
        : t('lensAdmin.timeline.notConnected')
    },
    {
      key: 'online',
      label: t('lensAdmin.timeline.online'),
      tone: node.status === 'online' ? 'done' : 'idle',
      meta:
        node.status === 'online' && node.last_heartbeat_at
          ? t('lensAdmin.timeline.heartbeat', {
              time: formatDateTime(node.last_heartbeat_at)
            })
          : t(`common.status.${node.status}`)
    }
  ]
})

function dotClass(tone) {
  return (
    {
      done: 'bg-success-500',
      error: 'bg-danger-500',
      pending: 'bg-warning-400',
      idle: 'bg-ink-300'
    }[tone] || 'bg-ink-300'
  )
}

function metaClass(tone) {
  return (
    {
      error: 'text-danger-600',
      pending: 'text-warning-700'
    }[tone] || 'text-ink-500'
  )
}

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
