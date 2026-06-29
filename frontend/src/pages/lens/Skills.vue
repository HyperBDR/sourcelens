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
                  v-for="row in pagedSkills"
                  :key="row.uuid"
                  class="transition-colors hover:bg-line-soft"
                >
                  <td class="table-cell">
                    <button
                      type="button"
                      class="text-left font-medium text-ink-900 hover:text-primary-700 hover:underline"
                      @click="openDetail(row)"
                    >
                      {{ row.name }}
                    </button>
                    <div
                      v-if="skillDescription(row)"
                      class="mt-1 max-w-xl truncate text-xs text-ink-500"
                    >
                      {{ skillDescription(row) }}
                    </div>
                  </td>
                  <td class="table-cell font-mono text-ink-500">
                    {{ row.slug }}
                  </td>
                  <td class="table-cell">
                    <span
                      v-if="isWorkspaceGuideSkill(row)"
                      class="inline-block rounded-md border border-primary-200 bg-primary-50 px-1.5 py-0.5 text-xs font-medium text-primary-700"
                      :title="t('lensAdmin.columns.workspaceGuideHint')"
                    >
                      {{ t('lensAdmin.columns.workspaceGuideTag') }}
                    </span>
                    <span v-else class="text-sm text-ink-400">
                      {{ t('lensAdmin.pages.skills.label') }}
                    </span>
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
          <PaginationBar
            v-if="!loading"
            v-model:page-size="pageSize"
            :current-page="currentPage"
            :total="skills.length"
            @page-size-change="handlePageSizeChange"
            @prev="goPrevPage"
            @next="goNextPage"
          />
        </div>
      </section>

      <BaseDrawer
        :show="showModal"
        :title="modalTitle"
        :subtitle="form.name || ''"
        @close="closeModal"
      >
        <form id="skill-form" class="space-y-4" @submit.prevent="save">
          <FormRow :label="t('lensAdmin.fields.name')" required>
            <input v-model="form.name" class="form-input" required />
          </FormRow>
          <FormRow :label="t('lensAdmin.fields.slug')" required>
            <input v-model="form.slug" class="form-input" required />
          </FormRow>
          <FormRow :label="t('lensAdmin.fields.description')">
            <input
              v-model="form.description"
              class="form-input"
              :placeholder="t('lensAdmin.placeholders.skillDescription')"
            />
          </FormRow>
          <FormRow :label="t('lensAdmin.fields.content')">
            <div class="mb-2 flex items-center justify-between gap-2">
              <span class="text-xs text-ink-400">
                {{ t('lensAdmin.skills.beautifyHint') }}
              </span>
              <BaseButton
                size="sm"
                variant="outline"
                :loading="beautifying"
                :disabled="beautifying"
                @click="beautify"
              >
                {{ t('lensAdmin.skills.beautify') }}
              </BaseButton>
            </div>
            <textarea
              v-model="form.content"
              class="form-input min-h-96"
              :placeholder="t('lensAdmin.placeholders.skillContent')"
            />
          </FormRow>
          <BooleanRow v-model="form.enabled" />

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
              form="skill-form"
            >
              {{ t('common.save') }}
            </BaseButton>
            <BaseButton variant="outline" @click="closeModal">
              {{ t('common.cancel') }}
            </BaseButton>
          </div>
        </template>
      </BaseDrawer>

      <BaseDrawer
        :show="showDetail"
        :title="t('lensAdmin.skillDetail.title')"
        @close="closeDetail"
      >
        <template #actions>
          <BaseButton size="sm" variant="outline" @click="editFromDetail">
            {{ t('common.edit') }}
          </BaseButton>
        </template>
        <div v-if="detailRow" class="space-y-5">
          <div class="space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              <StatusBadge
                :status="detailRow.enabled ? 'enabled' : 'disabled'"
              />
              <h3 class="text-base font-semibold text-ink-900">
                {{ detailRow.name }}
              </h3>
              <span
                v-if="isWorkspaceGuideSkill(detailRow)"
                class="inline-block rounded-md border border-primary-200 bg-primary-50 px-1.5 py-0.5 text-xs font-medium text-primary-700"
                :title="t('lensAdmin.columns.workspaceGuideHint')"
              >
                {{ t('lensAdmin.columns.workspaceGuideTag') }}
              </span>
              <span
                v-else
                class="inline-block rounded-md border border-line bg-surface-sunken px-1.5 py-0.5 text-xs font-medium text-ink-500"
              >
                {{ t('lensAdmin.pages.skills.label') }}
              </span>
            </div>
            <p class="font-mono text-xs text-ink-500">{{ detailRow.slug }}</p>
          </div>

          <div v-if="skillDescription(detailRow)">
            <div class="mb-1 text-sm font-medium text-ink-700">
              {{ t('lensAdmin.fields.description') }}
            </div>
            <p class="text-sm leading-6 text-ink-600">
              {{ skillDescription(detailRow) }}
            </p>
          </div>

          <div>
            <div class="mb-2 text-sm font-medium text-ink-700">
              {{ t('lensAdmin.fields.content') }}
            </div>
            <div
              v-if="skillContent(detailRow)"
              class="rounded-lg border border-line bg-surface-sunken p-4"
            >
              <MarkdownRenderer :content="skillContent(detailRow)" />
            </div>
            <p v-else class="text-sm text-ink-400">
              {{ t('common.noData') }}
            </p>
          </div>
        </div>
      </BaseDrawer>
    </div>
  </AdminLayout>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import AdminLayout from '@/admin/layout/AdminLayout.vue'
import {
  beautifySkill,
  createSkill,
  deleteSkill,
  listSkills,
  updateSkill
} from '@/api/lens'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import MarkdownRenderer from '@/components/ui/MarkdownRenderer.vue'
import PaginationBar from '@/components/ui/PaginationBar.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import { extractErrorMessage } from '@/utils/api'

import BooleanRow from './components/BooleanRow.vue'
import FormRow from './components/FormRow.vue'
import RowActions from './components/RowActions.vue'
import { normalizeList } from './adminHelpers'

const { t } = useI18n()
const { showSuccess, showError } = useToast()

const skills = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const saving = ref(false)
const beautifying = ref(false)
const showModal = ref(false)
const showDetail = ref(false)
const detailRow = ref(null)
const mode = ref('create')
const form = ref({})
const formError = ref('')

const columns = computed(() =>
  ['skill', 'slug', 'type', 'status', 'actions'].map((column) =>
    t(`lensAdmin.columns.${column}`)
  )
)

const totalPages = computed(() =>
  Math.max(1, Math.ceil(skills.value.length / pageSize.value))
)
const pagedSkills = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return skills.value.slice(start, start + pageSize.value)
})

function handlePageSizeChange() {
  currentPage.value = 1
}

function goPrevPage() {
  if (currentPage.value <= 1) return
  currentPage.value -= 1
}

function goNextPage() {
  if (currentPage.value >= totalPages.value) return
  currentPage.value += 1
}

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

function skillDescription(row) {
  const definition = row?.definition
  if (definition && typeof definition === 'object') {
    return definition.description || ''
  }
  return ''
}

function skillContent(row) {
  const definition = row?.definition
  if (typeof definition === 'string') {
    return definition
  }
  if (definition && typeof definition === 'object') {
    return (
      definition.content || definition.markdown || definition.skill_md || ''
    )
  }
  return ''
}

function defaultForm() {
  return {
    name: '',
    slug: '',
    description: '',
    content: '',
    enabled: true
  }
}

function formFromRow(row) {
  return {
    uuid: row.uuid,
    name: row.name || '',
    slug: row.slug || '',
    description: skillDescription(row),
    content: skillContent(row),
    enabled: row.enabled !== false
  }
}

function buildPayload() {
  const definition = { content: form.value.content || '' }
  const description = (form.value.description || '').trim()
  if (description) {
    definition.description = description
  }
  return {
    name: form.value.name,
    slug: form.value.slug,
    definition,
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

function openDetail(row) {
  detailRow.value = row
  showDetail.value = true
}

function closeDetail() {
  showDetail.value = false
  detailRow.value = null
}

function editFromDetail() {
  const row = detailRow.value
  closeDetail()
  if (row) {
    startEdit(row)
  }
}

async function beautify() {
  beautifying.value = true
  try {
    const result = await beautifySkill({
      name: form.value.name || '',
      content: form.value.content || ''
    })
    if (result?.content) {
      form.value.content = result.content
      showSuccess(t('lensAdmin.skills.beautifySuccess'))
    }
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.skills.beautifyFailed')))
  } finally {
    beautifying.value = false
  }
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

.table-head {
  @apply border-b border-line px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-500;
}

.table-cell {
  @apply px-4 py-4 text-sm text-ink-700;
}
</style>
