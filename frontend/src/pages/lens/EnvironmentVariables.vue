<template>
  <AdminLayout>
    <div class="flex max-w-full flex-col gap-4 py-4">
      <section
        class="overflow-hidden rounded-lg border border-line bg-surface shadow-sm"
      >
        <div
          class="flex flex-wrap items-start justify-between gap-4 border-b border-line px-5 py-4"
        >
          <div class="space-y-2">
            <h1 class="text-xl font-semibold text-ink-900">
              {{ t('lensAdmin.pages.environmentVariables.title') }}
            </h1>
            <p class="max-w-3xl text-sm leading-6 text-ink-500">
              {{ t('lensAdmin.pages.environmentVariables.description') }}
            </p>
          </div>
          <BaseButton variant="primary" size="sm" @click="startCreate">
            {{ t('lensAdmin.pages.environmentVariables.action') }}
          </BaseButton>
        </div>

        <BaseLoading v-if="loading" />
        <div
          v-else-if="!rows.length"
          class="px-5 py-12 text-center text-sm text-ink-500"
        >
          {{ t('lensAdmin.environmentVariables.empty') }}
        </div>
        <div v-else class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead
              class="border-b border-line bg-surface-sunken text-xs text-ink-500"
            >
              <tr>
                <th class="px-5 py-3">{{ t('lensAdmin.fields.name') }}</th>
                <th class="px-5 py-3">
                  {{ t('lensAdmin.environmentVariables.keys') }}
                </th>
                <th class="px-5 py-3">{{ t('lensAdmin.fields.status') }}</th>
                <th class="px-5 py-3 text-right">{{ t('common.actions') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="row in rows"
                :key="row.uuid"
                class="border-b border-line last:border-b-0"
              >
                <td class="px-5 py-4">
                  <div class="font-medium text-ink-900">{{ row.name }}</div>
                  <div v-if="row.description" class="mt-1 text-xs text-ink-500">
                    {{ row.description }}
                  </div>
                </td>
                <td class="px-5 py-4 font-mono text-xs text-ink-600">
                  {{ (row.keys || []).join(', ') || '—' }}
                </td>
                <td class="px-5 py-4">
                  <StatusBadge :status="row.enabled ? 'enabled' : 'disabled'" />
                </td>
                <td class="px-5 py-4 text-right">
                  <div class="flex justify-end gap-2">
                    <BaseButton
                      size="sm"
                      variant="outline"
                      @click="startEdit(row)"
                    >
                      {{ t('common.edit') }}
                    </BaseButton>
                    <BaseButton size="sm" variant="danger" @click="remove(row)">
                      {{ t('common.delete') }}
                    </BaseButton>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <BaseDrawer
        :show="showDrawer"
        :title="drawerTitle"
        :subtitle="form.name || ''"
        @close="closeDrawer"
      >
        <form
          id="environment-set-form"
          class="space-y-4"
          @submit.prevent="save"
        >
          <FormRow :label="t('lensAdmin.fields.name')" required>
            <input v-model="form.name" class="form-input" required />
          </FormRow>
          <FormRow :label="t('lensAdmin.fields.description')">
            <input v-model="form.description" class="form-input" />
          </FormRow>
          <FormRow :label="t('lensAdmin.environmentVariables.values')">
            <div class="overflow-hidden rounded-lg border border-line">
              <div
                class="flex justify-end border-b border-line bg-surface-sunken p-2"
              >
                <BaseButton size="sm" variant="outline" @click="addValue">
                  {{ t('lensAdmin.environmentVariables.addValue') }}
                </BaseButton>
              </div>
              <div v-if="!form.values.length" class="p-4 text-sm text-ink-400">
                {{ t('lensAdmin.environmentVariables.noValues') }}
              </div>
              <div
                v-for="(item, index) in form.values"
                :key="index"
                class="grid gap-2 border-b border-line p-3 last:border-b-0 sm:grid-cols-[0.8fr_1.2fr_auto]"
              >
                <input
                  v-model.trim="item.key"
                  class="form-input font-mono"
                  pattern="[A-Z_][A-Z0-9_]*"
                  :placeholder="t('lensAdmin.skills.environmentKey')"
                  required
                />
                <input
                  v-model="item.value"
                  class="form-input font-mono"
                  type="password"
                  :placeholder="t('lensAdmin.environmentVariables.value')"
                />
                <BaseButton
                  size="sm"
                  variant="outline"
                  @click="removeValue(index)"
                >
                  {{ t('common.delete') }}
                </BaseButton>
              </div>
            </div>
          </FormRow>
          <label class="flex items-center gap-2 text-sm text-ink-700">
            <input v-model="form.enabled" type="checkbox" />
            {{ t('lensAdmin.fields.enabled') }}
          </label>
          <p v-if="formError" class="text-sm text-danger-700">
            {{ formError }}
          </p>
        </form>
        <template #footer>
          <div class="flex flex-row-reverse gap-2">
            <BaseButton
              form="environment-set-form"
              type="submit"
              :loading="saving"
            >
              {{ t('common.save') }}
            </BaseButton>
            <BaseButton variant="outline" @click="closeDrawer">
              {{ t('common.cancel') }}
            </BaseButton>
          </div>
        </template>
      </BaseDrawer>
    </div>
  </AdminLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import AdminLayout from '@/admin/layout/AdminLayout.vue'
import {
  createEnvironmentVariableSet,
  deleteEnvironmentVariableSet,
  listEnvironmentVariableSets,
  revealEnvironmentVariableSet,
  updateEnvironmentVariableSet
} from '@/api/lens'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { useToast } from '@/composables/useToast'
import { extractErrorMessage } from '@/utils/api'

import FormRow from './components/FormRow.vue'
import { normalizeList } from './adminHelpers'

const { t } = useI18n()
const { showSuccess, showError } = useToast()
const rows = ref([])
const loading = ref(false)
const saving = ref(false)
const showDrawer = ref(false)
const mode = ref('create')
const form = ref(defaultForm())
const formError = ref('')

const drawerTitle = computed(() =>
  mode.value === 'create'
    ? t('lensAdmin.environmentVariables.createTitle')
    : t('lensAdmin.environmentVariables.editTitle')
)

function defaultForm() {
  return {
    uuid: '',
    name: '',
    description: '',
    values: [],
    enabled: true
  }
}

async function load() {
  loading.value = true
  try {
    rows.value = normalizeList(await listEnvironmentVariableSets())
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.loadFailed')))
  } finally {
    loading.value = false
  }
}

function startCreate() {
  mode.value = 'create'
  form.value = defaultForm()
  formError.value = ''
  showDrawer.value = true
}

async function startEdit(row) {
  mode.value = 'edit'
  formError.value = ''
  try {
    const revealed = await revealEnvironmentVariableSet(row.uuid)
    form.value = {
      uuid: row.uuid,
      name: row.name || '',
      description: row.description || '',
      values: (revealed.values || []).map((item) => ({ ...item })),
      enabled: row.enabled !== false
    }
    showDrawer.value = true
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.loadFailed')))
  }
}

function closeDrawer() {
  showDrawer.value = false
  form.value = defaultForm()
  formError.value = ''
}

function addValue() {
  form.value.values.push({ key: '', value: '' })
}

function removeValue(index) {
  form.value.values.splice(index, 1)
}

function payload() {
  return {
    name: form.value.name.trim(),
    description: form.value.description.trim(),
    values: form.value.values.map((item) => ({
      key: item.key.trim(),
      value: item.value
    })),
    enabled: !!form.value.enabled
  }
}

async function save() {
  saving.value = true
  formError.value = ''
  try {
    if (mode.value === 'create') {
      await createEnvironmentVariableSet(payload())
    } else {
      await updateEnvironmentVariableSet(form.value.uuid, payload())
    }
    showSuccess(t('lensAdmin.messages.saveSuccess'))
    closeDrawer()
    await load()
  } catch (error) {
    formError.value = extractErrorMessage(
      error,
      t('lensAdmin.messages.saveFailed')
    )
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  if (!window.confirm(t('lensAdmin.environmentVariables.deleteConfirm'))) {
    return
  }
  try {
    await deleteEnvironmentVariableSet(row.uuid)
    showSuccess(t('lensAdmin.messages.deleteSuccess'))
    await load()
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.deleteFailed')))
  }
}

onMounted(load)
</script>
