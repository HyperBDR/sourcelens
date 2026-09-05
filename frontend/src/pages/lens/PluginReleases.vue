<template>
  <AdminLayout>
    <div class="flex max-w-full flex-col gap-4 py-4">
      <section
        class="overflow-hidden rounded-lg border border-line bg-surface shadow-sm"
      >
        <header
          class="flex flex-col gap-4 border-b border-line px-5 py-4 md:flex-row md:items-start md:justify-between"
        >
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-xl font-semibold text-ink-900">
                {{ t('lensAdmin.pages.pluginReleases.title') }}
              </h1>
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1 text-xs text-ink-500"
              >
                {{ releases.length }}
              </span>
            </div>
            <p class="mt-1 text-sm text-ink-500">
              {{ t('lensAdmin.pages.pluginReleases.description') }}
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <BaseButton
              size="sm"
              variant="outline"
              :loading="reconciling"
              @click="reconcile"
            >
              {{ t('lensAdmin.pluginReleases.reconcile') }}
            </BaseButton>
            <BaseButton
              size="sm"
              variant="outline"
              :loading="loading"
              @click="load"
            >
              {{ t('common.refresh') }}
            </BaseButton>
          </div>
        </header>

        <div class="px-5 py-4">
          <BaseLoading v-if="loading && releases.length === 0" />
          <div
            v-else-if="releases.length === 0"
            class="rounded-xl border border-dashed border-line bg-surface-sunken px-6 py-16 text-center"
          >
            <p class="text-sm font-medium text-ink-700">
              {{ t('lensAdmin.pluginReleases.empty') }}
            </p>
          </div>
          <div v-else class="space-y-3">
            <article
              v-for="release in releases"
              :key="release.uuid"
              class="rounded-xl border border-line bg-surface p-4"
            >
              <div
                class="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between"
              >
                <div class="min-w-0 flex-1">
                  <div class="flex flex-wrap items-center gap-2">
                    <h2 class="font-semibold text-ink-900">
                      {{ release.display_name }}
                    </h2>
                    <code
                      class="rounded border border-line bg-surface-sunken px-2 py-0.5 text-xs text-ink-600"
                    >
                      {{ release.plugin_key }}@{{ release.version }}
                    </code>
                    <span
                      class="rounded-full border px-2 py-0.5 text-xs font-medium"
                      :class="releaseStatusClass(release.release_status)"
                    >
                      {{ releaseStatusLabel(release.release_status) }}
                    </span>
                    <span
                      v-if="release.deployment_role"
                      class="rounded-full border px-2 py-0.5 text-xs font-medium"
                      :class="releaseRoleClass(release.deployment_role)"
                    >
                      {{ releaseRoleLabel(release.deployment_role) }}
                    </span>
                  </div>
                  <p
                    v-if="release.description"
                    class="mt-2 max-w-3xl text-sm leading-5 text-ink-600"
                  >
                    {{ release.description }}
                  </p>
                  <dl class="mt-3 flex flex-wrap gap-x-6 gap-y-2 text-xs">
                    <div>
                      <dt class="inline text-ink-500">
                        {{ t('lensAdmin.pluginReleases.installation') }}
                      </dt>
                      <dd class="ml-1 inline font-medium text-ink-700">
                        {{
                          release.installed
                            ? t('lensAdmin.pluginReleases.installed')
                            : t('lensAdmin.pluginReleases.missing')
                        }}
                      </dd>
                    </div>
                    <div>
                      <dt class="inline text-ink-500">
                        {{ t('lensAdmin.pluginReleases.integrity') }}
                      </dt>
                      <dd
                        class="ml-1 inline font-medium"
                        :class="
                          release.integrity_ok === false
                            ? 'text-danger-700'
                            : 'text-ink-700'
                        "
                      >
                        {{ integrityLabel(release.integrity_ok) }}
                      </dd>
                    </div>
                    <div v-if="release.published_at">
                      <dt class="inline text-ink-500">
                        {{ t('lensAdmin.pluginReleases.publishedAt') }}
                      </dt>
                      <dd class="ml-1 inline font-medium text-ink-700">
                        {{ formatDateTime(release.published_at) }}
                      </dd>
                    </div>
                  </dl>
                </div>

                <div class="flex shrink-0 flex-wrap gap-2">
                  <BaseButton
                    v-if="release.release_status === 'debugging'"
                    size="sm"
                    variant="primary"
                    :loading="isMutating(release, 'publish')"
                    :disabled="!release.installed || hasMutation"
                    @click="publishRelease(release)"
                  >
                    {{ t('lensAdmin.pluginReleases.publish') }}
                  </BaseButton>
                  <template v-if="release.release_status === 'published'">
                    <BaseButton
                      v-if="release.deployment_role !== 'candidate'"
                      size="sm"
                      variant="outline"
                      :loading="isMutating(release, 'candidate')"
                      :disabled="!canPromote(release)"
                      @click="setRole(release, 'candidate')"
                    >
                      {{ t('lensAdmin.pluginReleases.setCandidate') }}
                    </BaseButton>
                    <BaseButton
                      v-if="release.deployment_role !== 'active'"
                      size="sm"
                      variant="primary"
                      :loading="isMutating(release, 'active')"
                      :disabled="!canPromote(release)"
                      @click="setRole(release, 'active')"
                    >
                      {{ t('lensAdmin.pluginReleases.setActive') }}
                    </BaseButton>
                    <BaseButton
                      v-if="release.deployment_role"
                      size="sm"
                      variant="outline"
                      :loading="isMutating(release, 'clear')"
                      :disabled="hasMutation"
                      @click="setRole(release, '')"
                    >
                      {{ t('lensAdmin.pluginReleases.clearRole') }}
                    </BaseButton>
                    <BaseButton
                      v-if="!release.deployment_role"
                      size="sm"
                      variant="outline"
                      :loading="isMutating(release, 'retire')"
                      :disabled="hasMutation"
                      @click="retireRelease(release)"
                    >
                      {{ t('lensAdmin.pluginReleases.retire') }}
                    </BaseButton>
                  </template>
                </div>
              </div>
            </article>
          </div>
        </div>
      </section>
    </div>
  </AdminLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import AdminLayout from '@/admin/layout/AdminLayout.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import {
  listPluginReleases,
  publishPluginRelease,
  reconcilePluginReleases,
  retirePluginRelease,
  setPluginReleaseRole
} from '@/api/lens'
import { useToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/utils/api'

const { locale, t } = useI18n()
const { showError, showSuccess } = useToast()

const releases = ref([])
const loading = ref(false)
const reconciling = ref(false)
const mutation = ref(null)
const hasMutation = computed(() => mutation.value !== null)

async function load() {
  loading.value = true
  try {
    releases.value = await listPluginReleases()
  } catch (error) {
    showError(
      extractErrorMessage(error, t('lensAdmin.pluginReleases.loadFailed'))
    )
  } finally {
    loading.value = false
  }
}

async function reconcile() {
  reconciling.value = true
  try {
    await reconcilePluginReleases()
    showSuccess(t('lensAdmin.pluginReleases.reconcileSuccess'))
    await load()
  } catch (error) {
    showError(
      extractErrorMessage(error, t('lensAdmin.pluginReleases.reconcileFailed'))
    )
  } finally {
    reconciling.value = false
  }
}

async function publishRelease(release) {
  await mutate(release, 'publish', () =>
    publishPluginRelease(release.plugin_key, release.version)
  )
}

async function setRole(release, role) {
  const action = role || 'clear'
  await mutate(release, action, () =>
    setPluginReleaseRole(release.plugin_key, release.version, role)
  )
}

async function retireRelease(release) {
  if (!window.confirm(t('lensAdmin.pluginReleases.retireConfirm'))) return
  await mutate(release, 'retire', () =>
    retirePluginRelease(release.plugin_key, release.version)
  )
}

async function mutate(release, action, request) {
  mutation.value = `${release.uuid}:${action}`
  try {
    await request()
    showSuccess(t('lensAdmin.pluginReleases.actionSuccess'))
    await load()
  } catch (error) {
    showError(
      extractErrorMessage(error, t('lensAdmin.pluginReleases.actionFailed'))
    )
  } finally {
    mutation.value = null
  }
}

function isMutating(release, action) {
  return mutation.value === `${release.uuid}:${action}`
}

function canPromote(release) {
  return (
    !hasMutation.value && release.installed && release.integrity_ok !== false
  )
}

function releaseStatusLabel(status) {
  return t(`lensAdmin.pluginReleases.status.${status}`)
}

function releaseStatusClass(status) {
  return {
    debugging: 'border-warning-200 bg-warning-50 text-warning-800',
    published: 'border-success-200 bg-success-50 text-success-700',
    retired: 'border-line bg-surface-sunken text-ink-500'
  }[status]
}

function releaseRoleLabel(role) {
  return t(`lensAdmin.pluginReleases.role.${role}`)
}

function releaseRoleClass(role) {
  return role === 'active'
    ? 'border-brand-200 bg-brand-50 text-brand-700'
    : 'border-warning-200 bg-warning-50 text-warning-800'
}

function integrityLabel(integrity) {
  if (integrity === true) return t('lensAdmin.pluginReleases.integrityValid')
  if (integrity === false) return t('lensAdmin.pluginReleases.integrityInvalid')
  return t('lensAdmin.pluginReleases.integrityMutable')
}

function formatDateTime(value) {
  return new Intl.DateTimeFormat(locale.value, {
    dateStyle: 'medium',
    timeStyle: 'short'
  }).format(new Date(value))
}

onMounted(load)
</script>
