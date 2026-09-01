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
                {{ t('lensAdmin.pages.connections.title') }}
              </h1>
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1 text-xs text-ink-500"
              >
                {{ connections.length }}
              </span>
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

        <div class="px-5 py-4">
          <BaseLoading v-if="loading && !connections.length" />
          <div
            v-else-if="!connections.length"
            class="rounded-lg border border-line bg-surface-sunken py-16 text-center text-sm text-ink-500"
          >
            {{ t('common.noData') }}
          </div>
          <div v-else class="overflow-x-auto rounded-lg border border-line">
            <table class="min-w-[58rem] w-full divide-y divide-line">
              <thead class="bg-surface-sunken">
                <tr>
                  <th class="table-head">
                    {{ t('lensAdmin.connections.name') }}
                  </th>
                  <th class="table-head">Plugin</th>
                  <th class="table-head">
                    {{ t('lensAdmin.connections.scope') }}
                  </th>
                  <th class="table-head">
                    {{ t('lensAdmin.connections.usage') }}
                  </th>
                  <th class="table-head">
                    {{ t('lensAdmin.connections.status') }}
                  </th>
                  <th class="table-head">
                    {{ t('lensAdmin.connections.actions') }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line bg-surface">
                <tr v-for="row in connections" :key="row.uuid">
                  <td class="table-cell">
                    <div class="font-medium text-ink-900">{{ row.name }}</div>
                    <div class="mt-1 text-xs text-ink-500">
                      {{
                        row.has_secret
                          ? t('lensAdmin.connections.secretStored')
                          : t('lensAdmin.connections.secretMissing')
                      }}
                    </div>
                  </td>
                  <td class="table-cell text-ink-600">{{ row.plugin_key }}</td>
                  <td class="table-cell text-ink-600">
                    <div class="max-w-sm break-words font-mono text-xs">
                      {{ repositoryScope(row) }}
                    </div>
                  </td>
                  <td class="table-cell text-ink-600">
                    {{ row.datasource_count }} / {{ row.assistant_count }}
                  </td>
                  <td class="table-cell">
                    <span
                      class="rounded border px-2 py-1 text-xs"
                      :class="
                        row.status === 'active'
                          ? 'border-success-200 bg-success-50 text-success-700'
                          : 'border-line bg-surface-sunken text-ink-500'
                      "
                    >
                      {{ row.status }}
                    </span>
                    <p
                      v-if="validationResults[row.uuid]"
                      class="mt-2 max-w-xs text-xs"
                      :class="
                        validationResults[row.uuid].ok
                          ? 'text-success-700'
                          : 'text-danger-700'
                      "
                    >
                      {{ validationResults[row.uuid].message }}
                    </p>
                  </td>
                  <td class="table-cell">
                    <div class="flex flex-wrap gap-2">
                      <BaseButton
                        size="sm"
                        variant="outline"
                        :loading="validatingUuid === row.uuid"
                        :disabled="row.status !== 'active'"
                        @click="validateRow(row)"
                      >
                        {{ t('lensAdmin.connections.validate') }}
                      </BaseButton>
                      <BaseButton
                        size="sm"
                        variant="outline"
                        @click="startEdit(row)"
                      >
                        {{ t('common.edit') }}
                      </BaseButton>
                      <BaseButton
                        size="sm"
                        variant="danger"
                        :loading="revokingUuid === row.uuid"
                        :disabled="row.status !== 'active'"
                        @click="revokeRow(row)"
                      >
                        {{ t('lensAdmin.connections.revoke') }}
                      </BaseButton>
                      <BaseButton
                        size="sm"
                        variant="danger"
                        :disabled="
                          row.datasource_count > 0 || row.assistant_count > 0
                        "
                        @click="removeRow(row)"
                      >
                        {{ t('common.delete') }}
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
  revokeConnection,
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
const revokingUuid = ref('')
const drawerOpen = ref(false)
const mode = ref('create')
const formError = ref('')
const form = ref(defaultForm())

const manifest = computed(
  () => pluginManifests.value[form.value.plugin_key] || null
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

async function revokeRow(row) {
  if (!window.confirm(t('lensAdmin.connections.revokeConfirm'))) return
  revokingUuid.value = row.uuid
  try {
    await revokeConnection(row.uuid)
    showSuccess(t('lensAdmin.connections.revokeSuccess'))
    await load()
  } catch (error) {
    showError(
      extractErrorMessage(error, t('lensAdmin.connections.revokeFailed'))
    )
  } finally {
    revokingUuid.value = ''
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
