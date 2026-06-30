/**
 * Pure datasource helpers extracted from DataSources.vue.
 *
 * Every function here depends only on its arguments (no refs, no i18n, no
 * component state), so it can be shared between the page and its drawer
 * sub-components.
 */

import { EMPTY_VALUE } from './adminHelpers'

export function formatDocIds(docIds) {
  if (Array.isArray(docIds)) {
    return docIds.join(', ')
  }
  return docIds || EMPTY_VALUE
}

export function dataSourceRepository(row) {
  const config = row.config || {}
  if (row.source_type === 'git') {
    return config.organization_url || config.repo_url || EMPTY_VALUE
  }
  return (
    config.folder_url ||
    config.folder_token ||
    config.document_url ||
    EMPTY_VALUE
  )
}

export function dataSourceRepositories(row) {
  const repositories = row?.config?.repositories
  return Array.isArray(repositories) ? repositories : []
}

export function isOrganizationDataSource(row) {
  return dataSourceRepositories(row).length > 0
}

export function dataSourceBranch(row) {
  if (row.source_type === 'git') {
    return row.config?.branch || 'main'
  }
  return EMPTY_VALUE
}

export function syncTagClass(status) {
  const classes = {
    success: 'border-success-200 bg-success-50 text-success-700',
    failed: 'border-danger-200 bg-danger-50 text-danger-700',
    running: 'border-warning-200 bg-warning-50 text-warning-700',
    not_synced: 'border-line bg-surface-sunken text-ink-600',
    disabled: 'border-line bg-surface-sunken text-ink-500',
    policy: 'border-primary-200 bg-primary-50 text-primary-700'
  }
  return classes[status] || classes.not_synced
}

export function formatDataSourcePolicyLine(syncPolicy) {
  if (syncPolicy?.mode === 'crontab') {
    const cron = syncPolicy.cron || EMPTY_VALUE
    const timezone = syncPolicy.timezone || 'UTC'
    return `Crontab: ${cron} - ${timezone}`
  }
  const interval = syncPolicy?.interval_seconds || 3600
  return `Interval: ${interval}s`
}

export function isDataSourceSyncing(row) {
  return Boolean(row?.current_sync?.task_id)
}

export function isDataSourceEnabled(row) {
  return row?.status !== 'disabled'
}
