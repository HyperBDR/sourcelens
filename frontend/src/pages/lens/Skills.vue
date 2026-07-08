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
                    <div class="flex flex-wrap items-center gap-2">
                      <BaseButton
                        size="sm"
                        variant="outline"
                        @click="download(row)"
                      >
                        {{ t('lensAdmin.skills.download') }}
                      </BaseButton>
                      <RowActions
                        :row="row"
                        @edit="startEdit"
                        @delete="remove"
                      />
                    </div>
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
          <FormRow
            :label="
              mode === 'create'
                ? t('lensAdmin.skills.createMethod')
                : t('lensAdmin.skills.sourceType')
            "
            required
          >
            <select
              v-if="mode === 'create'"
              v-model="createMethod"
              class="form-input"
            >
              <option
                v-for="option in createMethodOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </option>
            </select>
            <div
              v-else
              class="rounded-lg border border-line bg-surface-sunken px-3 py-2 text-sm text-ink-700"
            >
              {{ activeMethodLabel }}
            </div>
            <p class="mt-1 text-xs leading-5 text-ink-500">
              {{ activeMethodDescription }}
            </p>
          </FormRow>

          <template v-if="activeMethod === 'manual'">
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
          </template>

          <template v-else-if="activeMethod === 'upload'">
            <FormRow :label="t('lensAdmin.skills.packageFile')" required>
              <input
                ref="packageInput"
                class="hidden"
                type="file"
                accept=".zip,application/zip"
                @change="handlePackageFileChange"
              />
              <button
                type="button"
                class="upload-dropzone"
                :class="{ 'upload-dropzone-active': packageDragging }"
                @click="triggerPackagePick"
                @dragover.prevent="packageDragging = true"
                @dragleave.prevent="packageDragging = false"
                @drop.prevent="handlePackageDrop"
              >
                <UploadCloudIcon class="h-8 w-8 text-brand-500" />
                <span class="text-sm font-medium text-ink-800">
                  {{
                    packageFileName || t('lensAdmin.skills.packageDropTitle')
                  }}
                </span>
                <span class="text-xs leading-5 text-ink-500">
                  {{
                    packageFileName
                      ? packageFileSize
                      : t('lensAdmin.skills.packageDropSubtitle')
                  }}
                </span>
              </button>
              <div
                v-if="packageFile"
                class="mt-2 flex items-center justify-between gap-3 rounded-md border border-line bg-surface-sunken px-3 py-2"
              >
                <div class="min-w-0">
                  <div class="truncate text-sm font-medium text-ink-800">
                    {{ packageFileName }}
                  </div>
                  <div class="text-xs text-ink-500">
                    {{ packageFileSize }}
                  </div>
                </div>
                <button
                  type="button"
                  class="rounded-md p-1 text-ink-400 hover:bg-line-soft hover:text-ink-700"
                  :aria-label="t('common.delete')"
                  @click="clearPackageFile"
                >
                  <XIcon class="h-4 w-4" />
                </button>
              </div>
              <p class="mt-1 text-xs leading-5 text-ink-500">
                {{ t('lensAdmin.skills.packageFileHelp') }}
              </p>
            </FormRow>
          </template>

          <template v-else-if="activeMethod === 'github'">
            <FormRow :label="t('lensAdmin.skills.githubUrl')" required>
              <input
                v-model="githubUrl"
                class="form-input"
                required
                placeholder="https://github.com/owner/repository"
              />
              <p class="mt-1 text-xs leading-5 text-ink-500">
                {{ t('lensAdmin.skills.githubUrlHelp') }}
              </p>
            </FormRow>
          </template>

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
              {{ saveButtonLabel }}
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
          <BaseButton size="sm" variant="outline" @click="download(detailRow)">
            {{ t('lensAdmin.skills.download') }}
          </BaseButton>
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

          <div class="grid gap-3 sm:grid-cols-2">
            <div class="rounded-lg border border-line bg-surface-sunken p-3">
              <div class="text-xs font-medium text-ink-400">
                {{ t('lensAdmin.skills.sourceType') }}
              </div>
              <div class="mt-1 text-sm text-ink-700">
                {{ skillSourceType(detailRow) }}
              </div>
            </div>
            <div class="rounded-lg border border-line bg-surface-sunken p-3">
              <div class="text-xs font-medium text-ink-400">
                {{ t('lensAdmin.skills.files') }}
              </div>
              <div class="mt-1 text-sm text-ink-700">
                {{ skillFileCount(detailRow) }}
              </div>
            </div>
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

      <BaseModal
        :show="showDeleteModal"
        :title="t('lensAdmin.skills.deleteTitle')"
        icon-type="error"
        @close="closeDeleteModal"
      >
        <div v-if="deleteTarget" class="space-y-4">
          <p class="text-sm leading-6 text-ink-600">
            {{
              t('lensAdmin.skills.deleteRiskMessage', {
                name: deleteTarget.name
              })
            }}
          </p>
          <div
            v-if="deleteImpact.bound_assistants?.length"
            class="rounded-lg border border-danger-200 bg-danger-50 p-3"
          >
            <div class="text-sm font-medium text-danger-800">
              {{
                t('lensAdmin.skills.boundAssistants', {
                  count: deleteImpact.bound_count || 0
                })
              }}
            </div>
            <div class="mt-2 max-h-48 space-y-2 overflow-y-auto">
              <div
                v-for="assistant in deleteImpact.bound_assistants"
                :key="assistant.uuid"
                class="rounded-md border border-danger-100 bg-surface px-3 py-2"
              >
                <div class="text-sm font-medium text-ink-800">
                  {{ assistant.name }}
                </div>
                <div class="mt-1 text-xs text-ink-500">
                  {{ assistant.visibility }} · {{ assistant.status }} ·
                  {{ assistant.lensnode }}
                </div>
              </div>
            </div>
          </div>
          <FormRow :label="t('lensAdmin.skills.confirmSkillName')" required>
            <input
              v-model="deleteConfirmation"
              class="form-input"
              :placeholder="deleteTarget.name"
            />
            <p class="mt-1 text-xs leading-5 text-ink-500">
              {{
                t('lensAdmin.skills.confirmSkillNameHelp', {
                  name: deleteTarget.name
                })
              }}
            </p>
          </FormRow>
        </div>
        <template #footer>
          <div class="flex flex-row-reverse gap-2">
            <BaseButton
              variant="danger"
              :loading="deleting"
              :disabled="deleteConfirmation !== deleteTarget?.name"
              @click="confirmForceDelete"
            >
              {{ t('common.delete') }}
            </BaseButton>
            <BaseButton variant="outline" @click="closeDeleteModal">
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
import { UploadCloud as UploadCloudIcon, X as XIcon } from '@lucide/vue'

import AdminLayout from '@/admin/layout/AdminLayout.vue'
import {
  beautifySkill,
  createSkill,
  deleteSkill,
  downloadSkill,
  forceDeleteSkill,
  getSkillDeleteImpact,
  importSkillFromGithub,
  listSkills,
  updateGithubSkill,
  updateSkill,
  updateUploadedSkill,
  uploadSkill
} from '@/api/lens'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
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

const MAX_SKILL_PACKAGE_BYTES = 20 * 1024 * 1024

const skills = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const saving = ref(false)
const beautifying = ref(false)
const showModal = ref(false)
const showDetail = ref(false)
const showDeleteModal = ref(false)
const detailRow = ref(null)
const mode = ref('create')
const form = ref({})
const formError = ref('')
const githubUrl = ref('')
const editSourceType = ref('manual')
const packageFile = ref(null)
const packageInput = ref(null)
const packageDragging = ref(false)
const deleteTarget = ref(null)
const deleteImpact = ref({})
const deleteConfirmation = ref('')
const deleting = ref(false)

const createMethodOptions = computed(() => [
  {
    value: 'manual',
    label: t('lensAdmin.skills.manualCreate'),
    description: t('lensAdmin.skills.manualCreateHelp')
  },
  {
    value: 'upload',
    label: t('lensAdmin.skills.upload'),
    description: t('lensAdmin.skills.uploadHelp')
  },
  {
    value: 'github',
    label: t('lensAdmin.skills.importGithub'),
    description: t('lensAdmin.skills.importGithubHelp')
  }
])

const createMethod = ref('manual')

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

const saveButtonLabel = computed(() => {
  if (mode.value === 'edit' || createMethod.value === 'manual') {
    return t('common.save')
  }
  if (createMethod.value === 'upload') {
    return t('lensAdmin.skills.upload')
  }
  return t('lensAdmin.skills.importGithub')
})

const createMethodDescription = computed(() => {
  return (
    createMethodOptions.value.find(
      (option) => option.value === createMethod.value
    )?.description || ''
  )
})

const activeMethod = computed(() =>
  mode.value === 'edit' ? editSourceType.value : createMethod.value
)

const activeMethodOption = computed(() =>
  createMethodOptions.value.find(
    (option) => option.value === activeMethod.value
  )
)

const activeMethodLabel = computed(() => activeMethodOption.value?.label || '')

const activeMethodDescription = computed(() => {
  if (mode.value === 'create') {
    return createMethodDescription.value
  }
  if (activeMethod.value === 'upload') {
    return t('lensAdmin.skills.updateUploadHelp')
  }
  if (activeMethod.value === 'github') {
    return t('lensAdmin.skills.updateGithubHelp')
  }
  return activeMethodOption.value?.description || ''
})

const packageFileName = computed(() => packageFile.value?.name || '')

const packageFileSize = computed(() => {
  if (!packageFile.value) {
    return ''
  }
  const size = packageFile.value.size || 0
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`
  }
  return `${(size / 1024 / 1024).toFixed(1)} MB`
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

function skillSourceType(row) {
  return row?.source_type || 'manual'
}

function skillFileCount(row) {
  return row?.package_manifest?.file_count || 0
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

function handlePackageFileChange(event) {
  setPackageFile(event.target.files?.[0])
}

function triggerPackagePick() {
  packageInput.value?.click()
}

function handlePackageDrop(event) {
  packageDragging.value = false
  setPackageFile(event.dataTransfer?.files?.[0])
}

function setPackageFile(file) {
  if (!file) {
    return
  }
  if (!file.name.toLowerCase().endsWith('.zip')) {
    const message = t('lensAdmin.skills.packageFileInvalidType')
    formError.value = message
    showError(message)
    clearPackageFile()
    return
  }
  if (file.size > MAX_SKILL_PACKAGE_BYTES) {
    const message = t('lensAdmin.skills.packageFileTooLarge')
    formError.value = message
    showError(message)
    clearPackageFile()
    return
  }
  packageFile.value = file
  formError.value = ''
}

function clearPackageFile() {
  packageFile.value = null
  if (packageInput.value) {
    packageInput.value.value = ''
  }
}

function startCreate() {
  mode.value = 'create'
  createMethod.value = 'manual'
  editSourceType.value = 'manual'
  formError.value = ''
  form.value = defaultForm()
  githubUrl.value = ''
  packageFile.value = null
  showModal.value = true
}

function startEdit(row) {
  mode.value = 'edit'
  editSourceType.value = row?.source_type || 'manual'
  createMethod.value = editSourceType.value
  formError.value = ''
  form.value = formFromRow(row)
  githubUrl.value = row?.source_url || ''
  packageFile.value = null
  showModal.value = true
}

function closeModal() {
  showModal.value = false
  form.value = {}
  formError.value = ''
  githubUrl.value = ''
  editSourceType.value = 'manual'
  packageFile.value = null
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
    if (mode.value === 'create' && createMethod.value === 'upload') {
      if (!packageFile.value) {
        throw new Error(t('lensAdmin.skills.packageFileRequired'))
      }
      await uploadSkill(packageFile.value)
      showSuccess(t('lensAdmin.skills.uploadSuccess'))
    } else if (mode.value === 'create' && createMethod.value === 'github') {
      await importSkillFromGithub(githubUrl.value)
      showSuccess(t('lensAdmin.skills.importSuccess'))
    } else if (mode.value === 'edit' && activeMethod.value === 'upload') {
      if (!packageFile.value) {
        throw new Error(t('lensAdmin.skills.packageFileRequired'))
      }
      await updateUploadedSkill(form.value.uuid, packageFile.value)
      showSuccess(t('lensAdmin.messages.saveSuccess'))
    } else if (mode.value === 'edit' && activeMethod.value === 'github') {
      await updateGithubSkill(form.value.uuid, githubUrl.value)
      showSuccess(t('lensAdmin.messages.saveSuccess'))
    } else {
      await saveByMode(form.value.uuid, buildPayload())
      showSuccess(t('lensAdmin.messages.saveSuccess'))
    }
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
    const impact = await getSkillDeleteImpact(row.uuid)
    if ((impact?.bound_count || 0) > 0) {
      deleteTarget.value = row
      deleteImpact.value = impact || {}
      deleteConfirmation.value = ''
      showDeleteModal.value = true
      return
    }
    await deleteSkill(row.uuid)
    showSuccess(t('lensAdmin.messages.deleteSuccess'))
    await load()
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.deleteFailed')))
  }
}

function closeDeleteModal() {
  if (deleting.value) return
  showDeleteModal.value = false
  deleteTarget.value = null
  deleteImpact.value = {}
  deleteConfirmation.value = ''
}

async function confirmForceDelete() {
  if (!deleteTarget.value) return
  deleting.value = true
  try {
    await forceDeleteSkill(deleteTarget.value.uuid, deleteConfirmation.value)
    showSuccess(t('lensAdmin.messages.deleteSuccess'))
    deleting.value = false
    closeDeleteModal()
    await load()
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.deleteFailed')))
  } finally {
    deleting.value = false
  }
}

async function download(row) {
  if (!row?.uuid) return
  try {
    const response = await downloadSkill(row.uuid)
    const blob = new Blob([response.data], {
      type: response.headers?.['content-type'] || 'application/zip'
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `${row.slug || 'skill'}.zip`
    link.click()
    URL.revokeObjectURL(url)
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.skills.downloadFailed')))
  }
}

onMounted(load)
</script>

<style scoped>
.form-input {
  @apply w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}

.upload-dropzone {
  @apply flex w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-line bg-surface-sunken px-4 py-8 text-center transition-colors hover:border-brand-200 hover:bg-brand-50/40 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}

.upload-dropzone-active {
  @apply border-brand-200 bg-brand-50;
}

.table-head {
  @apply border-b border-line px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-500;
}

.table-cell {
  @apply px-4 py-4 text-sm text-ink-700;
}
</style>
