<template>
  <BaseDrawer
    :show="show"
    :title="t('lensAdmin.datasourceDetail.title')"
    :subtitle="datasource?.name || ''"
    width="2xl"
    @close="$emit('close')"
  >
    <template #actions>
      <BaseButton
        v-if="datasource?.current_sync?.id"
        size="sm"
        variant="outline"
        @click="$emit('open-task', datasource)"
      >
        {{ t('lensAdmin.actions.viewTask') }}
      </BaseButton>
    </template>
    <div v-if="datasource" class="space-y-6">
      <section>
        <h3 class="mb-4 text-sm font-semibold text-ink-900">
          {{ t('lensAdmin.datasourceDetail.basicInfo') }}
        </h3>
        <dl class="grid grid-cols-1 gap-4">
          <div>
            <dt
              class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600"
            >
              {{ t('lensAdmin.fields.name') }}
            </dt>
            <dd class="break-words text-sm font-medium text-ink-900">
              {{ datasource.name || emptyValue }}
            </dd>
          </div>
          <div>
            <dt
              class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600"
            >
              UUID
            </dt>
            <dd class="break-words font-mono text-xs font-medium text-ink-900">
              {{ datasource.uuid }}
            </dd>
          </div>
          <div>
            <dt
              class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600"
            >
              {{ t('lensAdmin.fields.status') }}
            </dt>
            <dd>
              <StatusBadge :status="datasource.status" />
            </dd>
          </div>
        </dl>
      </section>

      <section class="border-t border-line pt-6">
        <h3 class="mb-4 text-sm font-semibold text-ink-900">
          {{ t('lensAdmin.datasourceDetail.connection') }}
        </h3>
        <dl class="grid grid-cols-1 gap-4">
          <div v-for="item in datasourceConnectionDetails" :key="item.label">
            <dt
              class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600"
            >
              {{ item.label }}
            </dt>
            <dd
              class="break-words text-sm font-medium text-ink-900"
              :class="item.mono ? 'font-mono text-xs' : ''"
            >
              {{ item.value }}
            </dd>
          </div>
        </dl>
      </section>

      <section class="border-t border-line pt-6">
        <h3 class="mb-4 text-sm font-semibold text-ink-900">
          {{ t('lensAdmin.datasourceDetail.sync') }}
        </h3>
        <dl class="grid grid-cols-1 gap-4">
          <div v-for="item in datasourceSyncDetails" :key="item.label">
            <dt
              class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600"
            >
              {{ item.label }}
            </dt>
            <dd
              class="break-words text-sm font-medium text-ink-900"
              :class="item.mono ? 'font-mono text-xs' : ''"
            >
              {{ item.value }}
            </dd>
          </div>
        </dl>
      </section>
    </div>
    <div v-else class="py-12 text-center text-sm text-ink-500">
      {{ t('lensAdmin.datasourceDetail.selectHint') }}
    </div>
  </BaseDrawer>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'

import { EMPTY_VALUE as emptyValue } from './adminHelpers'
import { formatDocIds } from './datasourceHelpers'
import { useShortDateTime } from './useShortDateTime'

const props = defineProps({
  show: { type: Boolean, default: false },
  datasource: { type: Object, default: null },
  lensnodes: { type: Array, default: () => [] }
})

defineEmits(['close', 'open-task'])

const { t } = useI18n()
const formatDateTime = useShortDateTime()

function formatSourceType(sourceType) {
  if (sourceType === 'git') {
    return 'Git'
  }
  if (sourceType === 'feishu') {
    return t('lensAdmin.datasourceWizard.feishu')
  }
  return sourceType || emptyValue
}

function authSchemeLabel(authScheme) {
  if (authScheme === 'token') {
    return t('lensAdmin.datasourceWizard.authToken')
  }
  return t('lensAdmin.datasourceWizard.authNone')
}

function feishuScopeLabel(syncMode) {
  if (syncMode === 'drive_folder') {
    return t('lensAdmin.datasourceWizard.feishuScopeDriveFolder')
  }
  return t('lensAdmin.datasourceWizard.feishuScopeDocuments')
}

function formatSyncPolicy(syncPolicy) {
  if (syncPolicy?.mode === 'crontab') {
    const cron = syncPolicy.cron || emptyValue
    const timezone = syncPolicy.timezone || 'UTC'
    return `${cron} · ${timezone}`
  }
  const interval = syncPolicy?.interval_seconds
  return interval
    ? t('lensAdmin.table.intervalSeconds', { seconds: interval })
    : emptyValue
}

function lensNodeName(value) {
  const uuid = typeof value === 'object' ? value?.uuid : value
  const found = props.lensnodes.find((lensnode) => lensnode.uuid === uuid)
  return found?.name || uuid || emptyValue
}

function detailItem(label, value, mono = false) {
  const normalized = Array.isArray(value) ? value.join(', ') : value
  return {
    label,
    value: normalized || emptyValue,
    mono
  }
}

const datasourceConnectionDetails = computed(() => {
  const row = props.datasource
  if (!row) return []
  const config = row.config || {}
  if (row.source_type === 'git') {
    return [
      detailItem(t('lensAdmin.fields.type'), formatSourceType(row.source_type)),
      detailItem(t('lensAdmin.fields.repoUrl'), config.repo_url, true),
      detailItem(t('lensAdmin.fields.branch'), config.branch || 'main', true),
      detailItem(
        t('lensAdmin.fields.authScheme'),
        authSchemeLabel(config.auth_scheme)
      ),
      detailItem(
        t('lensAdmin.datasourceDetail.credential'),
        row.credential_configured
          ? t('common.status.enabled')
          : t('common.status.disabled')
      )
    ]
  }
  return [
    detailItem(t('lensAdmin.fields.type'), formatSourceType(row.source_type)),
    detailItem(
      t('lensAdmin.fields.syncScope'),
      feishuScopeLabel(config.sync_mode)
    ),
    detailItem(t('lensAdmin.fields.folderUrl'), config.folder_url, true),
    detailItem(t('lensAdmin.fields.folderToken'), config.folder_token, true),
    detailItem(t('lensAdmin.fields.documentUrl'), config.document_url, true),
    detailItem(t('lensAdmin.fields.docIds'), formatDocIds(config.doc_ids), true)
  ].filter((item) => item.value !== emptyValue)
})

const datasourceSyncDetails = computed(() => {
  const row = props.datasource
  if (!row) return []
  return [
    detailItem(
      t('lensAdmin.fields.lensnode'),
      row.lensnode_name || lensNodeName(row.lensnode)
    ),
    detailItem(t('lensAdmin.fields.targetPath'), row.target_path, true),
    detailItem(
      t('lensAdmin.fields.syncInterval'),
      formatSyncPolicy(row.sync_policy)
    ),
    detailItem(
      t('lensAdmin.datasourceDetail.lastSyncedAt'),
      formatDateTime(row.last_synced_at)
    ),
    detailItem(t('lensAdmin.datasourceDetail.lastError'), row.last_error, true),
    detailItem(
      t('lensAdmin.datasourceDetail.createdAt'),
      formatDateTime(row.created_at)
    ),
    detailItem(
      t('lensAdmin.datasourceDetail.updatedAt'),
      formatDateTime(row.updated_at)
    )
  ]
})
</script>
