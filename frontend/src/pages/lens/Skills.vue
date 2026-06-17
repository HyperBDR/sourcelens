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
                {{ t('lensAdmin.pages.skills.title') }}
              </h1>
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1 text-xs font-medium text-ink-500"
              >
                {{ t('lensAdmin.pages.skills.label') }}
              </span>
            </div>
            <p class="max-w-3xl text-sm leading-6 text-ink-500">
              {{ t('lensAdmin.pages.skills.description') }}
            </p>
            <div class="flex flex-wrap items-center gap-2 text-xs text-ink-500">
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1"
              >
                {{
                  t('lensAdmin.total', {
                    label: t('lensAdmin.pages.skills.label'),
                    count: skills.length
                  })
                }}
              </span>
              <span
                class="rounded-md border border-line bg-surface-sunken px-2 py-1"
              >
                {{ t('lensAdmin.pages.skills.action') }}
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
              {{ t('lensAdmin.pages.skills.action') }}
            </BaseButton>
          </div>
        </div>

        <div class="px-5 py-4">
          <BaseLoading v-if="loading && skills.length === 0" />

          <div
            v-else-if="skills.length === 0"
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
                    v-for="column in columns"
                    :key="column"
                    class="table-head"
                  >
                    {{ column }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line bg-surface">
                <tr
                  v-for="row in skills"
                  :key="row.uuid"
                  class="transition-colors hover:bg-line-soft"
                >
                  <td class="table-cell font-medium text-ink-900">
                    {{ row.name }}
                    <span
                      v-if="isWorkspaceGuideSkill(row)"
                      class="ml-2 inline-block rounded-md border border-primary-200 bg-primary-50 px-1.5 py-0.5 text-xs font-medium text-primary-700"
                      :title="t('lensAdmin.columns.workspaceGuideHint')"
                    >
                      {{ t('lensAdmin.columns.workspaceGuideTag') }}
                    </span>
                  </td>
                  <td class="table-cell font-mono text-ink-500">
                    {{ row.slug }}
                  </td>
                  <td class="table-cell">
                    <StatusBadge
                      :status="row.enabled ? 'enabled' : 'disabled'"
                    />
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

      <BaseModal :show="showModal" :title="modalTitle" @close="closeModal">
        <form class="space-y-4" @submit.prevent="save">
          <FormRow :label="t('lensAdmin.fields.name')">
            <input v-model="form.name" class="form-input" required />
          </FormRow>
          <FormRow :label="t('lensAdmin.fields.slug')">
            <input v-model="form.slug" class="form-input" required />
          </FormRow>
          <FormRow :label="t('lensAdmin.fields.definition')">
            <textarea
              v-model="form.definition_text"
              class="json-input"
              rows="6"
            />
          </FormRow>
          <BooleanRow v-model="form.enabled" />

          <p v-if="formError" class="text-sm text-danger-700">
            {{ formError }}
          </p>
        </form>
        <template #footer>
          <div class="flex flex-row-reverse gap-2">
            <BaseButton :loading="saving" variant="primary" @click="save">
              {{ t('common.save') }}
            </BaseButton>
            <BaseButton variant="outline" @click="closeModal">
              {{ t('common.cancel') }}
            </BaseButton>
          </div>
        </template>
      </BaseModal>
    </div>
  </AdminLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import AdminLayout from '@/admin/layout/AdminLayout.vue'
import { createSkill, deleteSkill, listSkills, updateSkill } from '@/api/lens'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { extractErrorMessage } from '@/utils/api'

import BooleanRow from './components/BooleanRow.vue'
import FormRow from './components/FormRow.vue'
import RowActions from './components/RowActions.vue'
import { normalizeList, stringifyJson } from './adminHelpers'

const { t } = useI18n()
const { showSuccess, showError } = useToast()

const skills = ref([])
const loading = ref(false)
const saving = ref(false)
const showModal = ref(false)
const mode = ref('create')
const form = ref({})
const formError = ref('')

const columns = computed(() =>
  ['skill', 'slug', 'status', 'actions'].map((column) =>
    t(`lensAdmin.columns.${column}`)
  )
)

const modalTitle = computed(() => {
  const action =
    mode.value === 'create'
      ? t('lensAdmin.modal.create')
      : t('lensAdmin.modal.edit')
  return `${action} ${t('lensAdmin.pages.skills.label')}`
})

function isWorkspaceGuideSkill(row) {
  return typeof row?.slug === 'string' && row.slug.endsWith('-workspace-guide')
}

function defaultForm() {
  return {
    name: '',
    slug: '',
    definition_text: '',
    enabled: true
  }
}

function formFromRow(row) {
  return {
    uuid: row.uuid,
    name: row.name || '',
    slug: row.slug || '',
    definition_text:
      typeof row.definition === 'string'
        ? row.definition
        : stringifyJson(row.definition || {}),
    enabled: row.enabled !== false
  }
}

function buildPayload() {
  return {
    name: form.value.name,
    slug: form.value.slug,
    definition: form.value.definition_text,
    enabled: !!form.value.enabled
  }
}

async function load() {
  loading.value = true
  formError.value = ''
  try {
    skills.value = normalizeList(await listSkills())
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.loadFailed')))
  } finally {
    loading.value = false
  }
}

function startCreate() {
  mode.value = 'create'
  formError.value = ''
  form.value = defaultForm()
  showModal.value = true
}

function startEdit(row) {
  mode.value = 'edit'
  formError.value = ''
  form.value = formFromRow(row)
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  form.value = {}
  formError.value = ''
}

async function saveByMode(uuid, payload) {
  if (mode.value === 'create') {
    await createSkill(payload)
  } else {
    await updateSkill(uuid, payload)
  }
}

async function save() {
  saving.value = true
  formError.value = ''
  try {
    await saveByMode(form.value.uuid, buildPayload())
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

async function remove(row) {
  try {
    await deleteSkill(row.uuid)
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

.json-input {
  @apply w-full rounded-lg border border-line bg-surface px-3 py-2 font-mono text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}

.table-head {
  @apply border-b border-line px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-500;
}

.table-cell {
  @apply px-4 py-4 text-sm text-ink-700;
}
</style>
