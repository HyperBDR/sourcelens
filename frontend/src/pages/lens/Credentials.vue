<template>
  <AdminLayout>
    <div class="flex max-w-full flex-col gap-4 py-4">
      <section
        class="overflow-hidden rounded-lg border border-line bg-surface shadow-sm"
      >
        <div
          class="flex flex-col gap-4 border-b border-line px-5 py-4 lg:flex-row lg:items-start lg:justify-between"
        >
          <div class="min-w-0 space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-xl font-semibold text-ink-900">
                {{ t('lensAdmin.pages.credentials.title') }}
              </h1>
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1 text-xs font-medium text-ink-500"
              >
                {{ t('lensAdmin.pages.credentials.label') }}
              </span>
            </div>
            <p class="max-w-3xl text-sm leading-6 text-ink-500">
              {{ t('lensAdmin.pages.credentials.description') }}
            </p>
            <div class="flex flex-wrap items-center gap-2 text-xs text-ink-500">
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1"
              >
                {{
                  t('lensAdmin.total', {
                    label: t('lensAdmin.pages.credentials.label'),
                    count: credentials.length
                  })
                }}
              </span>
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1"
              >
                {{ t('lensAdmin.pages.credentials.action') }}
              </span>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <BaseButton
              variant="outline"
              size="sm"
              :loading="loading"
              @click="load"
            >
              {{ t('common.refresh') }}
            </BaseButton>
            <BaseButton variant="primary" size="sm" @click="startCreate">
              {{ t('lensAdmin.pages.credentials.action') }}
            </BaseButton>
          </div>
        </div>

        <div class="px-5 py-4">
          <BaseLoading v-if="loading && credentials.length === 0" />

          <div
            v-else-if="credentials.length === 0"
            class="rounded-lg border border-line bg-surface-sunken py-16 text-center"
          >
            <p class="text-sm font-medium text-ink-500">
              {{ t('common.noData') }}
            </p>
          </div>

          <div
            v-else
            class="relative overflow-x-auto rounded-lg border border-line bg-surface"
          >
            <table class="min-w-full divide-y divide-line">
              <thead class="bg-surface-sunken">
                <tr>
                  <th
                    v-for="column in activeColumns"
                    :key="column"
                    class="table-head"
                  >
                    {{ column }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line bg-surface">
                <tr
                  v-for="row in credentials"
                  :key="row.uuid"
                  class="transition-colors hover:bg-line-soft"
                >
                  <td class="table-cell">
                    <div class="font-medium text-ink-900">
                      {{ row.name }}
                    </div>
                    <div class="mt-1 text-xs text-ink-500">
                      {{
                        row.has_secret
                          ? t('lensAdmin.credentials.secretConfigured')
                          : t('lensAdmin.credentials.secretMissing')
                      }}
                    </div>
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ credentialProviderLabel(row.provider) }}
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ credentialAuthTypeLabel(row.auth_type) }}
                  </td>
                  <td class="table-cell text-ink-600">
                    <div
                      class="inline-flex"
                      @mouseenter="showCredentialBindings($event, row)"
                      @mouseleave="hideCredentialBindings"
                    >
                      <span
                        class="cursor-default underline decoration-dotted underline-offset-4"
                      >
                        {{ row.datasource_count || 0 }}
                      </span>
                    </div>
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ formatDateTime(row.last_used_at) }}
                  </td>
                  <td class="table-cell">
                    <RowActions :row="row" @edit="startEdit" @delete="remove" />
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <Teleport to="body">
        <div
          v-if="credentialBindingTooltip.row"
          class="pointer-events-none fixed z-[9999] w-64 rounded-md border border-line bg-surface p-3 text-xs shadow-lg"
          :style="credentialBindingTooltipStyle"
        >
          <div class="mb-2 font-medium text-ink-900">
            {{ t('lensAdmin.credentials.boundDatasources') }}
          </div>
          <div class="max-h-64 space-y-2 overflow-y-auto">
            <div
              v-for="datasource in credentialBindings(
                credentialBindingTooltip.row
              )"
              :key="datasource.uuid"
              class="rounded border border-line bg-surface-sunken px-2 py-1.5"
            >
              <div class="font-medium text-ink-900">
                {{ datasource.name }}
              </div>
              <div class="mt-0.5 text-ink-500">
                {{ formatSourceType(datasource.source_type) }}
                · {{ datasource.status }}
              </div>
            </div>
          </div>
        </div>
      </Teleport>

      <BaseDrawer
        :show="showModal"
        :title="modalTitle"
        :subtitle="form.name || ''"
        @close="closeModal"
      >
        <form id="credential-form" class="space-y-4" @submit.prevent="save">
          <FormRow :label="t('lensAdmin.fields.name')" required>
            <input v-model="form.name" class="form-input" required />
          </FormRow>
          <FormRow :label="t('lensAdmin.fields.type')" required>
            <select v-model="form.provider" class="form-input" required>
              <option value="generic">Git</option>
              <option value="feishu">Feishu</option>
            </select>
          </FormRow>
          <FormRow :label="t('lensAdmin.fields.authScheme')">
            <div class="form-input bg-surface-sunken text-ink-500">
              {{ credentialAuthTypeLabel(credentialFormAuthType) }}
            </div>
          </FormRow>
          <template v-if="credentialFormAuthType === 'feishu_app'">
            <FormRow :label="t('lensAdmin.fields.feishuAppId')" required>
              <input
                v-model="form.app_id"
                class="form-input"
                autocomplete="off"
                :placeholder="t('lensAdmin.credentials.appIdPlaceholder')"
                :required="mode === 'create'"
              />
            </FormRow>
            <FormRow :label="t('lensAdmin.fields.feishuAppSecret')" required>
              <div class="flex gap-2">
                <input
                  v-model="form.app_secret"
                  class="form-input"
                  :type="credentialSecretRevealed ? 'text' : 'password'"
                  autocomplete="off"
                  :placeholder="t('lensAdmin.credentials.appSecretPlaceholder')"
                  :required="mode === 'create'"
                />
                <button
                  v-if="canRevealCredential"
                  class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-line text-ink-500 hover:bg-surface-sunken hover:text-ink-900"
                  type="button"
                  :title="revealButtonTitle"
                  @click="toggleCredentialReveal"
                >
                  <component
                    :is="credentialSecretRevealed ? EyeOffIcon : EyeIcon"
                    class="h-4 w-4"
                  />
                </button>
              </div>
            </FormRow>
          </template>
          <FormRow v-else :label="t('lensAdmin.fields.accessToken')" required>
            <div class="flex gap-2">
              <input
                v-model="form.secret"
                class="form-input"
                :type="credentialSecretRevealed ? 'text' : 'password'"
                autocomplete="off"
                :placeholder="t('lensAdmin.credentials.tokenPlaceholder')"
                :required="mode === 'create'"
              />
              <button
                v-if="canRevealCredential"
                class="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-md border border-line text-ink-500 hover:bg-surface-sunken hover:text-ink-900"
                type="button"
                :title="revealButtonTitle"
                @click="toggleCredentialReveal"
              >
                <component
                  :is="credentialSecretRevealed ? EyeOffIcon : EyeIcon"
                  class="h-4 w-4"
                />
              </button>
            </div>
          </FormRow>
          <p v-if="mode === 'edit'" class="-mt-2 text-xs text-ink-500">
            {{ t('lensAdmin.credentials.replaceHint') }}
          </p>

          <p v-if="formError" class="text-sm text-danger-700">
            {{ formError }}
          </p>
        </form>
        <template #footer>
          <div class="flex flex-row-reverse gap-2">
            <BaseButton
              :loading="saving"
              variant="primary"
              type="submit"
              form="credential-form"
            >
              {{ t('common.save') }}
            </BaseButton>
            <BaseButton variant="outline" @click="closeModal">
              {{ t('common.cancel') }}
            </BaseButton>
          </div>
        </template>
      </BaseDrawer>
    </div>
  </AdminLayout>
</template>

<script setup>
import { Eye as EyeIcon, EyeOff as EyeOffIcon } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { extractErrorMessage } from '@/utils/api'
import AdminLayout from '@/admin/layout/AdminLayout.vue'
import {
  createCredential,
  deleteCredential,
  listCredentials,
  revealCredential,
  updateCredential
} from '@/api/lens'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'

import FormRow from './components/FormRow.vue'
import RowActions from './components/RowActions.vue'
import { EMPTY_VALUE as emptyValue, normalizeList } from './adminHelpers'
import { useShortDateTime } from './useShortDateTime'

const { t } = useI18n()
const { showSuccess, showError } = useToast()

const CREDENTIAL_MASK = '********'

const loading = ref(false)
const saving = ref(false)
const mode = ref('create')
const form = ref({})
const formError = ref('')
const showModal = ref(false)

const credentials = ref([])
const credentialSecretRevealed = ref(false)
const revealingCredential = ref(false)
const credentialBindingTooltip = ref({
  row: null,
  left: 0,
  top: 0
})

const formatDateTime = useShortDateTime()

const activeColumns = computed(() =>
  [
    'credential',
    'type',
    'authScheme',
    'datasources',
    'lastUsedAt',
    'actions'
  ].map((column) => t(`lensAdmin.columns.${column}`))
)

const modalTitle = computed(() => {
  const action =
    mode.value === 'create'
      ? t('lensAdmin.modal.create')
      : t('lensAdmin.modal.edit')
  return `${action} ${t('lensAdmin.pages.credentials.label')}`
})

const credentialFormAuthType = computed(() =>
  form.value.provider === 'feishu' ? 'feishu_app' : 'https_token'
)

const canRevealCredential = computed(
  () => mode.value === 'edit' && !!form.value.uuid
)

const revealButtonTitle = computed(() =>
  credentialSecretRevealed.value
    ? t('lensAdmin.credentials.hideSecret')
    : t('lensAdmin.credentials.revealSecret')
)

const credentialBindingTooltipStyle = computed(() => ({
  left: `${credentialBindingTooltip.value.left}px`,
  top: `${credentialBindingTooltip.value.top}px`
}))

function credentialProviderLabel(provider) {
  if (provider === 'feishu') {
    return 'Feishu'
  }
  if (provider) {
    return 'Git'
  }
  return emptyValue
}

function credentialAuthTypeLabel(authType) {
  const labels = {
    https_token: 'HTTPS Token',
    feishu_app: 'Feishu App'
  }
  return labels[authType] || authType || emptyValue
}

function formatSourceType(sourceType) {
  if (sourceType === 'git') {
    return 'Git'
  }
  if (sourceType === 'feishu') {
    return t('lensAdmin.datasourceWizard.feishu')
  }
  return sourceType || emptyValue
}

function credentialBindings(row) {
  return Array.isArray(row?.datasource_bindings) ? row.datasource_bindings : []
}

function showCredentialBindings(event, row) {
  if (!credentialBindings(row).length) {
    return
  }
  const rect = event.currentTarget.getBoundingClientRect()
  const tooltipWidth = 256
  const tooltipGap = 8
  const estimatedHeight = Math.min(
    280,
    46 + credentialBindings(row).length * 48
  )
  const left = Math.min(
    Math.max(8, rect.left),
    window.innerWidth - tooltipWidth - 8
  )
  const top =
    rect.top > estimatedHeight + tooltipGap
      ? rect.top - estimatedHeight - tooltipGap
      : rect.bottom + tooltipGap
  credentialBindingTooltip.value = {
    row,
    left,
    top
  }
}

function hideCredentialBindings() {
  credentialBindingTooltip.value = {
    row: null,
    left: 0,
    top: 0
  }
}

async function toggleCredentialReveal() {
  if (!form.value.uuid || revealingCredential.value) {
    return
  }
  if (credentialSecretRevealed.value) {
    credentialSecretRevealed.value = false
    form.value.secret = form.value.secret ? CREDENTIAL_MASK : ''
    form.value.app_secret = form.value.app_secret ? CREDENTIAL_MASK : ''
    return
  }
  revealingCredential.value = true
  try {
    const payload = await revealCredential(form.value.uuid)
    if (credentialFormAuthType.value === 'feishu_app') {
      form.value.app_id = payload?.app_id || ''
      form.value.app_secret = payload?.app_secret || ''
    } else {
      form.value.secret = payload?.secret || ''
    }
    credentialSecretRevealed.value = true
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.loadFailed')))
  } finally {
    revealingCredential.value = false
  }
}

async function load() {
  loading.value = true
  formError.value = ''
  try {
    const credentialRows = await listCredentials()
    credentials.value = normalizeList(credentialRows)
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.loadFailed')))
  } finally {
    loading.value = false
  }
}

function startCreate() {
  mode.value = 'create'
  formError.value = ''
  credentialSecretRevealed.value = false
  revealingCredential.value = false
  form.value = defaultForm()
  showModal.value = true
}

function startEdit(row) {
  mode.value = 'edit'
  formError.value = ''
  credentialSecretRevealed.value = false
  revealingCredential.value = false
  form.value = formFromRow(row)
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  form.value = {}
  formError.value = ''
  credentialSecretRevealed.value = false
  revealingCredential.value = false
}

function defaultForm() {
  return {
    name: '',
    provider: 'generic',
    secret: '',
    app_id: '',
    app_secret: ''
  }
}

function formFromRow(row) {
  return {
    uuid: row.uuid,
    name: row.name || '',
    provider: row.auth_type === 'feishu_app' ? 'feishu' : 'generic',
    secret: row.masked_secret || '',
    app_id: row.masked_app_id || '',
    app_secret: row.masked_secret || ''
  }
}

async function save() {
  saving.value = true
  formError.value = ''
  try {
    const payload = buildPayload()
    const uuid = form.value.uuid
    if (mode.value === 'create') {
      await createCredential(payload)
    } else {
      await updateCredential(uuid, payload)
    }
    showSuccess(t('lensAdmin.messages.saveSuccess'))
    closeModal()
    await load()
  } catch (error) {
    formError.value = extractErrorMessage(
      error,
      t('lensAdmin.messages.saveFailed')
    )
    showError(formError.value)
  } finally {
    saving.value = false
  }
}

function buildPayload() {
  const payload = {
    name: form.value.name,
    provider: form.value.provider,
    auth_type: credentialFormAuthType.value
  }
  if (credentialFormAuthType.value === 'feishu_app') {
    if (form.value.app_id?.trim() && form.value.app_id !== CREDENTIAL_MASK) {
      payload.app_id = form.value.app_id.trim()
    }
    if (
      form.value.app_secret?.trim() &&
      form.value.app_secret !== CREDENTIAL_MASK
    ) {
      payload.app_secret = form.value.app_secret.trim()
    }
  } else if (
    form.value.secret?.trim() &&
    form.value.secret !== CREDENTIAL_MASK
  ) {
    payload.secret = form.value.secret.trim()
  }
  return payload
}

async function remove(row) {
  try {
    await deleteCredential(row.uuid)
    showSuccess(t('lensAdmin.messages.deleteSuccess'))
    await load()
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.deleteFailed')))
  }
}

onMounted(load)
</script>

<style scoped>
.form-input {
  @apply w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}

.table-head {
  @apply border-b border-line px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-500;
}

.table-cell {
  @apply px-4 py-4 text-sm text-ink-700;
}
</style>
