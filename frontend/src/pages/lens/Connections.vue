<template>
  <AdminLayout>
    <div class="flex max-w-full flex-col gap-5 py-4">
      <section
        class="overflow-hidden rounded-lg border border-line bg-surface shadow-sm"
      >
        <header
          class="flex flex-col gap-4 border-b border-line px-5 py-4 md:flex-row md:items-start md:justify-between"
        >
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-xl font-semibold text-ink-900">
                {{ t('lensAdmin.pages.connections.title') }}
              </h1>
            </div>
            <p class="mt-1 text-sm text-ink-500">
              {{ t('lensAdmin.pages.connections.description') }}
            </p>
          </div>
          <div class="flex items-center gap-2">
            <BaseButton
              size="sm"
              variant="outline"
              :loading="loading"
              @click="load"
            >
              {{ t('common.refresh') }}
            </BaseButton>
            <BaseButton size="sm" variant="primary" @click="startCreate">
              {{ t('lensAdmin.pages.connections.action') }}
            </BaseButton>
          </div>
        </header>

        <div class="grid gap-3 border-b border-line bg-surface-sunken px-5 py-4 sm:grid-cols-3">
          <div class="rounded-lg border border-line bg-surface px-4 py-3">
            <p class="text-xs font-medium uppercase tracking-wide text-ink-500">
              {{ t('lensAdmin.connections.total') }}
            </p>
            <p class="mt-1 text-2xl font-semibold text-ink-900">
              {{ connections.length }}
            </p>
          </div>
          <div class="rounded-lg border border-line bg-surface px-4 py-3">
            <p class="text-xs font-medium uppercase tracking-wide text-ink-500">
              {{ t('lensAdmin.connections.activeCount') }}
            </p>
            <p class="mt-1 text-2xl font-semibold text-success-700">
              {{ activeConnectionCount }}
            </p>
          </div>
          <div class="rounded-lg border border-line bg-surface px-4 py-3">
            <p class="text-xs font-medium uppercase tracking-wide text-ink-500">
              {{ t('lensAdmin.connections.pluginCount') }}
            </p>
            <p class="mt-1 text-2xl font-semibold text-brand-700">
              {{ pluginCount }}
            </p>
          </div>
        </div>

        <div class="px-5 py-5">
          <BaseLoading v-if="loading && !connections.length" />
          <div
            v-else-if="!connections.length"
            class="rounded-xl border border-dashed border-line bg-surface-sunken px-6 py-16 text-center"
          >
            <p class="text-sm font-medium text-ink-700">
              {{ t('common.noData') }}
            </p>
            <p class="mt-1 text-sm text-ink-500">
              {{ t('lensAdmin.connections.emptyHint') }}
            </p>
          </div>
          <div v-else class="grid gap-4 lg:grid-cols-2">
            <article
              v-for="row in connections"
              :key="row.uuid"
              class="rounded-xl border border-line bg-surface p-5 shadow-sm transition-shadow hover:shadow-md"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <div class="flex flex-wrap items-center gap-2">
                    <h2 class="truncate text-base font-semibold text-ink-900">
                      {{ row.name }}
                    </h2>
                    <span
                      class="rounded-full border px-2 py-0.5 text-xs font-medium"
                      :class="
                        row.status === 'active'
                          ? 'border-success-200 bg-success-50 text-success-700'
                          : 'border-line bg-surface-sunken text-ink-500'
                      "
                    >
                      {{ row.status }}
                    </span>
                  </div>
                  <p class="mt-1 text-sm text-ink-500">
                    {{ pluginDisplayName(row.plugin_key) }}
                  </p>
                </div>
                <span
                  class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-brand-50 text-sm font-semibold uppercase text-brand-700"
                  aria-hidden="true"
                >
                  {{ row.plugin_key.slice(0, 2) }}
                </span>
              </div>

              <dl class="mt-5 grid grid-cols-2 gap-4 border-y border-line py-4">
                <div>
                  <dt class="text-xs text-ink-500">{{ t('lensAdmin.connections.scope') }}</dt>
                  <dd class="mt-1 flex flex-wrap gap-1.5">
                    <span
                      v-for="item in scopeItems(row)"
                      :key="item"
                      class="max-w-full truncate rounded-md bg-surface-sunken px-2 py-1 font-mono text-xs text-ink-700"
                    >
                      {{ item }}
                    </span>
                  </dd>
                </div>
                <div>
                  <dt class="text-xs text-ink-500">{{ t('lensAdmin.connections.usage') }}</dt>
                  <dd class="mt-1 text-sm font-medium text-ink-800">
                    {{ row.datasource_count }} {{ t('lensAdmin.connections.datasources') }}
                    <span class="mx-1 text-ink-300">·</span>
                    {{ row.assistant_count }} {{ t('lensAdmin.connections.assistants') }}
                  </dd>
                </div>
              </dl>

              <div class="flex items-center justify-between gap-3">
                <span class="text-xs text-ink-500">
                  {{ row.has_secret ? t('lensAdmin.connections.secretStored') : t('lensAdmin.connections.secretMissing') }}
                </span>
                <div class="flex flex-wrap justify-end gap-2">
                  <BaseButton
                    size="sm"
                    variant="outline"
                    :loading="validatingUuid === row.uuid"
                    :disabled="row.status !== 'active'"
                    @click="validateRow(row)"
                  >
                    {{ t('lensAdmin.connections.validate') }}
                  </BaseButton>
                  <BaseButton size="sm" variant="outline" @click="startEdit(row)">
                    {{ t('common.edit') }}
                  </BaseButton>
                  <BaseButton
                    size="sm"
                    variant="danger"
                    :disabled="row.datasource_count > 0 || row.assistant_count > 0"
                    @click="removeRow(row)"
                  >
                    {{ t('common.delete') }}
                  </BaseButton>
                </div>
              </div>
              <p
                v-if="validationResults[row.uuid]"
                class="mt-3 text-xs"
                :class="validationResults[row.uuid].ok ? 'text-success-700' : 'text-danger-700'"
              >
                {{ validationResults[row.uuid].message }}
              </p>
            </article>
          </div>
        </div>
      </section>
    </div>

    <BaseDrawer
      :show="drawerOpen"
      :title="
        mode === 'create'
          ? t('lensAdmin.connections.createTitle')
          : t('lensAdmin.connections.editTitle')
      "
      @close="closeDrawer"
    >
      <div class="space-y-5">
        <div
          v-if="manifest"
          class="rounded-md border border-brand-200 bg-brand-50 p-3 text-sm text-brand-800"
        >
          <div class="font-medium">{{ manifest.display_name }}</div>
          <p class="mt-1 text-xs leading-5">{{ manifest.description }}</p>
        </div>
        <label class="block">
          <span class="mb-1 block text-sm font-medium text-ink-700">
            {{ t('lensAdmin.connections.name') }}
          </span>
          <input v-model="form.name" class="form-input" required />
        </label>
        <label class="block">
          <span class="mb-1 block text-sm font-medium text-ink-700">Plugin</span>
          <BaseSelect
            :model-value="form.plugin_key"
            :disabled="mode === 'edit'"
            @update:model-value="handlePluginChange"
          >
            <option
              v-for="plugin in plugins"
              :key="plugin.key"
              :value="plugin.key"
            >
              {{ plugin.display_name }}
            </option>
          </BaseSelect>
        </label>
        <ManifestSchemaForm
          v-if="manifest?.connection_schema"
          v-model="form"
          :schema="manifest.connection_schema"
        />
        <section
          v-if="connectionResourceField"
          class="rounded-lg border border-line bg-surface-sunken p-3"
        >
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p class="text-sm font-medium text-ink-800">
                {{ t('lensAdmin.connections.discoverResources') }}
              </p>
              <p class="mt-1 text-xs text-ink-500">
                {{ t('lensAdmin.connections.discoverResourcesHint') }}
              </p>
            </div>
            <BaseButton
              size="sm"
              variant="outline"
              :loading="discoveringResources"
              :disabled="!hasFieldValue(form.secret_value)"
              @click="discoverConnectionResources"
            >
              {{ t('lensAdmin.connections.discoverResourcesAction') }}
            </BaseButton>
          </div>
          <div
            v-if="connectionResourceCandidates.length"
            class="mt-3 max-h-48 space-y-1 overflow-y-auto rounded-md border border-line bg-surface p-2"
          >
            <label
              v-for="item in connectionResourceCandidates"
              :key="item.value"
              class="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-surface-sunken"
            >
              <input
                type="checkbox"
                :checked="selectedConnectionResource(item.value)"
                @change="toggleConnectionResource(item.value, $event.target.checked)"
              >
              <span class="min-w-0 truncate text-ink-800">{{ item.label }}</span>
              <span v-if="item.metadata?.private" class="text-xs text-ink-500">
                {{ t('lensAdmin.connections.privateResource') }}
              </span>
            </label>
          </div>
        </section>
        <p v-if="mode === 'edit'" class="-mt-2 text-xs text-ink-500">
          {{ t('lensAdmin.connections.tokenEditHint') }}
        </p>
        <label class="block">
          <span class="mb-1 block text-sm font-medium text-ink-700">
            {{ t('lensAdmin.connections.status') }}
          </span>
          <BaseSelect v-model="form.status">
            <option value="active">{{ t('common.status.active') }}</option>
            <option value="disabled">{{ t('common.status.disabled') }}</option>
          </BaseSelect>
        </label>
        <p v-if="formError" class="text-sm text-danger-700">{{ formError }}</p>
      </div>
      <template #footer>
        <div class="flex justify-end gap-2">
          <BaseButton variant="outline" @click="closeDrawer">
            {{ t('common.cancel') }}
          </BaseButton>
          <BaseButton
            variant="primary"
            :loading="saving"
            :disabled="!canSave"
            @click="save"
          >
            {{ t('common.save') }}
          </BaseButton>
        </div>
      </template>
    </BaseDrawer>
  </AdminLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import AdminLayout from '@/admin/layout/AdminLayout.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import BaseSelect from '@/components/ui/BaseSelect.vue'
import ManifestSchemaForm from '@/components/lens/ManifestSchemaForm.vue'
import {
  createConnection,
  deleteConnection,
  getConnectionResources,
  getPluginManifest,
  listConnections,
  listPlugins,
  previewConnectionResources,
  updateConnection,
  validateConnection
} from '@/api/lens'
import { useToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/utils/api'

const { t } = useI18n()
const { showError, showSuccess } = useToast()
const connections = ref([])
const plugins = ref([])
const pluginManifests = ref({})
const loading = ref(false)
const saving = ref(false)
const validatingUuid = ref('')
const validationResults = ref({})
const drawerOpen = ref(false)
const mode = ref('create')
const formError = ref('')
const form = ref(defaultForm())
const discoveringResources = ref(false)
const connectionResourceCandidates = ref([])

const activeConnectionCount = computed(
  () => connections.value.filter((row) => row.status === 'active').length
)
const pluginCount = computed(
  () => new Set(connections.value.map((row) => row.plugin_key)).size
)

const manifest = computed(
  () => pluginManifests.value[form.value.plugin_key] || null
)
const connectionResourceField = computed(() =>
  Object.entries(manifest.value?.connection_schema?.properties || {}).find(
    ([, field]) => field.type === 'array' && field.format === 'provider-resource'
  )
)

const canSave = computed(() => {
  if (!form.value.name.trim() || !manifest.value) return false
  const required = manifest.value.connection_schema?.required || []
  return required.every((key) => {
    const field = manifest.value.connection_schema.properties?.[key]
    if (mode.value === 'edit' && field?.format === 'password') return true
    return hasFieldValue(form.value[key])
  })
})

function defaultForm() {
  const pluginKey = plugins.value[0]?.key || ''
  return {
    uuid: '',
    name: '',
    plugin_key: pluginKey,
    status: 'active',
    ...manifestDefaults(pluginKey)
  }
}

function hasFieldValue(value) {
  if (Array.isArray(value)) return value.length > 0
  return String(value ?? '').trim().length > 0
}

function repositoryScope(row) {
  const scope = row.allowed_scope || {}
  return Object.keys(scope).length ? JSON.stringify(scope) : '-'
}

function scopeItems(row) {
  const repositories = row.allowed_scope?.repositories
  if (Array.isArray(repositories) && repositories.length) return repositories
  return [repositoryScope(row)]
}

function pluginDisplayName(pluginKey) {
  return (
    pluginManifests.value[pluginKey]?.display_name ||
    pluginKey ||
    t('lensAdmin.connections.unknownPlugin')
  )
}

async function load() {
  loading.value = true
  try {
    const [connectionRows, installedPlugins] = await Promise.all([
      listConnections(),
      listPlugins()
    ])
    const manifests = await Promise.all(
      installedPlugins.map((plugin) => getPluginManifest(plugin.key))
    )
    connections.value = connectionRows
    plugins.value = installedPlugins
    pluginManifests.value = Object.fromEntries(
      manifests.map((item) => [item.key, item])
    )
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.connections.loadFailed')))
  } finally {
    loading.value = false
  }
}

function startCreate() {
  mode.value = 'create'
  form.value = defaultForm()
  formError.value = ''
  drawerOpen.value = true
}

function startEdit(row) {
  mode.value = 'edit'
  const nextForm = {
    uuid: row.uuid,
    name: row.name,
    plugin_key: row.plugin_key,
    status: row.status
  }
  const schema = pluginManifests.value[row.plugin_key]?.connection_schema
  Object.entries(schema?.properties || {}).forEach(([key, field]) => {
    nextForm[key] =
      field.format === 'password'
        ? ''
        : readConnectionField(row, field.write_to)
  })
  form.value = nextForm
  formError.value = ''
  drawerOpen.value = true
}

function closeDrawer() {
  drawerOpen.value = false
  formError.value = ''
  connectionResourceCandidates.value = []
}

async function discoverConnectionResources() {
  if (!connectionResourceField.value) return
  discoveringResources.value = true
  try {
    const [key, field] = connectionResourceField.value
    const result = await previewConnectionResources({
      plugin_key: form.value.plugin_key,
      secret_value: form.value.secret_value,
      endpoint: form.value.endpoint,
      config: buildConnectionPayload().config,
      limit: 50
    })
    connectionResourceCandidates.value =
      result.resources?.[field.resource]?.items || []
    if (!Array.isArray(form.value[key])) form.value[key] = []
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.connections.discoveryFailed')))
  } finally {
    discoveringResources.value = false
  }
}

function selectedConnectionResource(value) {
  const [key] = connectionResourceField.value || []
  return Array.isArray(form.value[key]) && form.value[key].includes(value)
}

function toggleConnectionResource(value, selected) {
  const [key] = connectionResourceField.value || []
  const current = Array.isArray(form.value[key]) ? form.value[key] : []
  form.value[key] = selected
    ? [...new Set([...current, value])]
    : current.filter((item) => item !== value)
}

async function save() {
  saving.value = true
  formError.value = ''
  const payload = buildConnectionPayload()
  try {
    if (mode.value === 'create') {
      await createConnection(payload)
    } else {
      await updateConnection(form.value.uuid, payload)
    }
    clearSecretFields()
    showSuccess(t('lensAdmin.connections.saveSuccess'))
    closeDrawer()
    await load()
  } catch (error) {
    clearSecretFields()
    formError.value = extractErrorMessage(
      error,
      t('lensAdmin.connections.saveFailed')
    )
    showError(formError.value)
  } finally {
    saving.value = false
  }
}

async function validateRow(row) {
  validatingUuid.value = row.uuid
  try {
    await validateConnection(row.uuid)
    const resources = await getConnectionResources(row.uuid)
    validationResults.value[row.uuid] = {
      ok: true,
      message: t('lensAdmin.connections.validationSuccess', {
        count: resourceItemCount(resources.resources)
      })
    }
  } catch (error) {
    validationResults.value[row.uuid] = {
      ok: false,
      message: extractErrorMessage(
        error,
        t('lensAdmin.connections.validationFailed')
      )
    }
  } finally {
    validatingUuid.value = ''
  }
}

function handlePluginChange(pluginKey) {
  form.value = {
    uuid: form.value.uuid,
    name: form.value.name,
    plugin_key: pluginKey,
    status: form.value.status,
    ...manifestDefaults(pluginKey)
  }
}

function manifestDefaults(pluginKey) {
  const schema = pluginManifests.value[pluginKey]?.connection_schema
  return Object.fromEntries(
    Object.entries(schema?.properties || {}).map(([key, field]) => [
      key,
      field.default ?? (field.type === 'array' ? [] : '')
    ])
  )
}

function readConnectionField(row, writeTo) {
  if (!writeTo) return ''
  return writeTo.split('.').reduce((value, key) => value?.[key], row) ?? ''
}

function buildConnectionPayload() {
  const payload = {
    name: form.value.name.trim(),
    plugin_key: form.value.plugin_key,
    config: {},
    allowed_scope: {},
    status: form.value.status
  }
  const fields = manifest.value?.connection_schema?.properties || {}
  Object.entries(fields).forEach(([key, field]) => {
    const value = form.value[key]
    if (field.format === 'password' && !hasFieldValue(value)) return
    writeConnectionField(payload, field.write_to, value)
  })
  return payload
}

function clearSecretFields() {
  const fields = manifest.value?.connection_schema?.properties || {}
  Object.entries(fields).forEach(([key, field]) => {
    if (field.format === 'password') form.value[key] = ''
  })
}

function writeConnectionField(payload, writeTo, value) {
  if (!writeTo) return
  const [section, key] = writeTo.split('.')
  if (key) payload[section][key] = value
  else payload[section] = value
}

function resourceItemCount(resources) {
  return Object.values(resources || {}).reduce(
    (total, collection) =>
      total + (Array.isArray(collection?.items) ? collection.items.length : 0),
    0
  )
}

async function removeRow(row) {
  if (!window.confirm(t('lensAdmin.connections.deleteConfirm'))) return
  try {
    await deleteConnection(row.uuid)
    showSuccess(t('lensAdmin.connections.deleteSuccess'))
    await load()
  } catch (error) {
    showError(
      extractErrorMessage(error, t('lensAdmin.connections.deleteFailed'))
    )
  }
}

onMounted(load)
</script>
