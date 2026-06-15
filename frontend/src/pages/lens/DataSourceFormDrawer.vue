<template>
  <BaseDrawer
    :show="show"
    :title="drawerTitle"
    :subtitle="drawerSubtitle"
    @close="$emit('close')"
  >
    <div class="mb-6 flex items-center">
      <template v-for="(step, i) in wizardStepsMeta" :key="step.key">
        <div class="flex flex-col items-center">
          <div
            class="flex h-8 w-8 items-center justify-center rounded-full border-2 text-sm font-medium transition-colors"
            :class="
              i + 1 < wizardStep
                ? 'border-brand-600 bg-brand-600 text-white'
                : i + 1 === wizardStep
                  ? 'border-brand-600 text-brand-600'
                  : 'border-line text-ink-400'
            "
          >
            <span v-if="i + 1 < wizardStep">✓</span>
            <span v-else>{{ i + 1 }}</span>
          </div>
          <span
            class="mt-1 text-xs"
            :class="
              i + 1 === wizardStep
                ? 'font-medium text-brand-600'
                : 'text-ink-400'
            "
          >
            {{ step.title }}
          </span>
        </div>
        <div
          v-if="i < wizardStepsMeta.length - 1"
          class="mb-4 mx-1 h-px flex-1 bg-line"
        />
      </template>
    </div>

    <div v-if="wizardStep === 1" class="space-y-5">
      <p class="text-sm text-ink-500">
        {{ t('lensAdmin.datasourceWizard.step1Desc') }}
      </p>
      <FormRow :label="t('lensAdmin.fields.name')" required>
        <input v-model="form.name" class="form-input" required />
      </FormRow>
      <FormRow :label="t('lensAdmin.fields.type')" required>
        <select
          v-model="form.source_type"
          class="form-input"
          @change="$emit('type-change')"
        >
          <option
            v-for="type in sourceTypes"
            :key="type.value"
            :value="type.value"
          >
            {{ type.label }}
          </option>
        </select>
        <p class="mt-1 text-xs text-ink-500">
          {{ selectedSourceTypeDescription }}
        </p>
      </FormRow>
      <FormRow :label="t('lensAdmin.fields.status')" required>
        <select v-model="form.status" class="form-input">
          <option value="active">{{ t('common.status.active') }}</option>
          <option value="disabled">{{ t('common.status.disabled') }}</option>
        </select>
      </FormRow>
    </div>

    <div v-else-if="wizardStep === 2" class="space-y-5">
      <p class="text-sm text-ink-500">
        {{ t('lensAdmin.datasourceWizard.step2Desc') }}
      </p>
      <FormRow :label="t('lensAdmin.fields.lensnode')" required>
        <select v-model="form.lensnode_uuid" class="form-input" required>
          <option value="">
            {{ t('lensAdmin.placeholders.selectLensNode') }}
          </option>
          <option
            v-for="node in onlineLensNodes"
            :key="node.uuid"
            :value="node.uuid"
          >
            {{ node.name }} · {{ node.workspace_path || '/workspace' }}
          </option>
        </select>
        <p class="mt-1 text-xs text-ink-500">
          {{ t('lensAdmin.datasourceWizard.onlineNodeHint') }}
        </p>
      </FormRow>
      <div
        v-if="!onlineLensNodes.length"
        class="rounded-md border border-warning-200 bg-warning-50 p-3 text-sm text-warning-800"
      >
        {{ t('lensAdmin.datasourceWizard.noOnlineNodes') }}
      </div>
    </div>

    <div v-else-if="wizardStep === 3" class="space-y-5">
      <p class="text-sm text-ink-500">
        {{ t('lensAdmin.datasourceWizard.step3Desc') }}
      </p>
      <template v-if="form.source_type === 'git'">
        <FormRow :label="t('lensAdmin.fields.repoUrl')" required>
          <input
            v-model="config.repo_url"
            class="form-input"
            placeholder="https://github.com/org/repo.git"
          />
          <p class="mt-1 text-xs text-ink-500">
            {{ t('lensAdmin.datasourceWizard.gitRepoHint') }}
          </p>
        </FormRow>
        <div class="grid gap-4 md:grid-cols-2">
          <FormRow :label="t('lensAdmin.fields.branch')">
            <input v-model="config.branch" class="form-input" />
          </FormRow>
          <FormRow :label="t('lensAdmin.fields.authScheme')" required>
            <select v-model="config.auth_scheme" class="form-input">
              <option value="none">
                {{ t('lensAdmin.datasourceWizard.authNone') }}
              </option>
              <option value="token">
                {{ t('lensAdmin.datasourceWizard.authToken') }}
              </option>
            </select>
          </FormRow>
        </div>
        <FormRow
          v-if="config.auth_scheme === 'token'"
          :label="t('lensAdmin.fields.accessToken')"
          :required="!form.credential_configured"
        >
          <input
            v-model="config.access_token"
            class="form-input"
            type="password"
            autocomplete="off"
          />
          <p class="mt-1 text-xs text-ink-500">
            {{
              form.credential_configured
                ? t('lensAdmin.datasourceWizard.accessTokenConfiguredHint')
                : t('lensAdmin.datasourceWizard.accessTokenHint')
            }}
          </p>
        </FormRow>
      </template>
      <template v-else>
        <FormRow :label="t('lensAdmin.fields.documentUrl')">
          <input
            v-model="config.document_url"
            class="form-input"
            placeholder="https://xxx.feishu.cn/docx/..."
          />
          <p class="mt-1 text-xs text-ink-500">
            {{ t('lensAdmin.datasourceWizard.feishuUrlHint') }}
          </p>
        </FormRow>
        <div class="grid gap-4 md:grid-cols-2">
          <FormRow :label="t('lensAdmin.fields.appToken')">
            <input v-model="config.app_token" class="form-input" />
          </FormRow>
        </div>
        <FormRow :label="t('lensAdmin.fields.docIds')">
          <input
            v-model="config.doc_ids_text"
            class="form-input"
            :placeholder="t('lensAdmin.placeholders.docIds')"
          />
          <p class="mt-1 text-xs text-ink-500">
            {{ t('lensAdmin.datasourceWizard.feishuDocHint') }}
          </p>
        </FormRow>
      </template>
      <div class="flex items-center gap-2">
        <BaseButton
          variant="outline"
          size="sm"
          :disabled="!canTestConnection"
          :loading="testingConnection"
          @click="$emit('test-connection')"
        >
          {{ t('lensAdmin.datasourceWizard.testConnection') }}
        </BaseButton>
      </div>
      <div
        v-if="connectionResult"
        class="rounded-md border p-3 text-sm"
        :class="
          connectionResult.status === 'success'
            ? 'border-success-200 bg-success-50 text-success-800'
            : 'border-danger-200 bg-danger-50 text-danger-800'
        "
      >
        {{ connectionResultMessage }}
      </div>
    </div>

    <div v-else-if="wizardStep === 4" class="space-y-5">
      <p class="text-sm text-ink-500">
        {{ t('lensAdmin.datasourceWizard.step4Desc') }}
      </p>
      <FormRow :label="t('lensAdmin.fields.targetPath')" required>
        <div class="flex overflow-hidden rounded-lg border border-line">
          <span
            class="flex items-center border-r border-line bg-surface-sunken px-3 font-mono text-sm text-ink-500"
          >
            {{ workspacePrefix }}
          </span>
          <input
            v-model="form.workspace_relative_path"
            class="min-w-0 flex-1 bg-surface px-3 py-2 font-mono text-sm text-ink-900 focus:outline-none"
            placeholder="repos/sourcelens"
            @blur="$emit('check-path')"
          />
        </div>
        <p class="mt-1 text-xs text-ink-500">
          {{ t('lensAdmin.datasourceWizard.pathHint') }}
        </p>
      </FormRow>
      <div class="flex items-center gap-2">
        <BaseButton
          variant="outline"
          size="sm"
          :disabled="!canCheckPath"
          :loading="checkingPath"
          @click="$emit('check-path')"
        >
          {{ t('lensAdmin.datasourceWizard.checkPath') }}
        </BaseButton>
        <span class="text-xs text-ink-400">
          {{ targetPath }}
        </span>
      </div>
      <div
        v-if="pathResult"
        class="rounded-md border p-3 text-sm"
        :class="
          pathResult.status === 'blocked'
            ? 'border-danger-200 bg-danger-50 text-danger-800'
            : 'border-success-200 bg-success-50 text-success-800'
        "
      >
        {{ pathResultMessage }}
      </div>
      <FormRow :label="t('lensAdmin.fields.syncInterval')" required>
        <input
          v-model.number="syncIntervalSeconds"
          class="form-input w-40"
          min="60"
          type="number"
        />
        <p class="mt-1 text-xs text-ink-500">
          {{ t('lensAdmin.datasourceWizard.intervalHint') }}
        </p>
      </FormRow>
    </div>

    <p v-if="formError" class="mt-4 text-sm text-danger-700">
      {{ formError }}
    </p>

    <template #footer>
      <div class="flex items-center justify-between">
        <BaseButton
          variant="outline"
          @click="wizardStep > 1 ? prevWizardStep() : $emit('close')"
        >
          {{ wizardStep > 1 ? t('lensAdmin.wizard.back') : t('common.cancel') }}
        </BaseButton>
        <div class="flex items-center gap-3">
          <span class="text-xs text-ink-400">
            {{ wizardStep }} / {{ WIZARD_STEP_COUNT }}
          </span>
          <BaseButton
            v-if="wizardStep < WIZARD_STEP_COUNT"
            variant="primary"
            :disabled="!canProceedWizard"
            @click="nextWizardStep"
          >
            {{ t('lensAdmin.wizard.next') }}
          </BaseButton>
          <BaseButton
            v-else
            variant="primary"
            :loading="saving"
            :disabled="
              pathResult?.status === 'blocked' ||
              connectionResult?.status !== 'success'
            "
            @click="$emit('save')"
          >
            {{ mode === 'create' ? t('lensAdmin.wizard.finish') : t('common.save') }}
          </BaseButton>
        </div>
      </div>
    </template>
  </BaseDrawer>
</template>

<script setup>
import { computed, defineComponent, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'

const props = defineProps({
  show: Boolean,
  mode: { type: String, default: 'create' },
  form: { type: Object, required: true },
  config: { type: Object, required: true },
  lensnodes: { type: Array, default: () => [] },
  syncIntervalSeconds: { type: Number, default: 3600 },
  pathResult: { type: Object, default: null },
  connectionResult: { type: Object, default: null },
  checkingPath: Boolean,
  testingConnection: Boolean,
  saving: Boolean,
  formError: { type: String, default: '' }
})

const emit = defineEmits([
  'close',
  'save',
  'type-change',
  'check-path',
  'test-connection',
  'connection-change',
  'update:syncIntervalSeconds'
])

const { t } = useI18n()
const WIZARD_STEP_COUNT = 4
const wizardStep = ref(1)

const syncIntervalSeconds = computed({
  get() {
    return props.syncIntervalSeconds
  },
  set(value) {
    emit('update:syncIntervalSeconds', value)
  }
})

const FormRow = defineComponent({
  props: {
    label: {
      type: String,
      required: true
    },
    required: {
      type: Boolean,
      default: false
    }
  },
  setup(rowProps, { slots }) {
    return () =>
      h('div', [
        h(
          'label',
          { class: 'mb-1 block text-sm font-medium text-ink-700' },
          [
            rowProps.label,
            rowProps.required
              ? h('span', { class: 'ml-0.5 text-danger-600' }, '*')
              : null
          ]
        ),
        slots.default?.()
      ])
  }
})

const drawerTitle = computed(() =>
  props.mode === 'create'
    ? t('lensAdmin.datasourceWizard.createTitle')
    : t('lensAdmin.datasourceWizard.editTitle')
)

const drawerSubtitle = computed(() =>
  props.mode === 'edit' ? props.form.name || '' : ''
)

const sourceTypes = computed(() => [
  {
    value: 'git',
    label: 'Git',
    description: t('lensAdmin.datasourceWizard.gitDesc')
  },
  {
    value: 'feishu',
    label: t('lensAdmin.datasourceWizard.feishu'),
    description: t('lensAdmin.datasourceWizard.feishuDesc')
  }
])

const selectedSourceTypeDescription = computed(() => {
  const selected = sourceTypes.value.find(
    (type) => type.value === props.form.source_type
  )
  return selected?.description || ''
})

const wizardStepsMeta = computed(() => [
  { key: 'basic', title: t('lensAdmin.datasourceWizard.step1Title') },
  { key: 'node', title: t('lensAdmin.datasourceWizard.step2Title') },
  { key: 'connection', title: t('lensAdmin.datasourceWizard.step3Title') },
  { key: 'sync', title: t('lensAdmin.datasourceWizard.step4Title') }
])

const onlineLensNodes = computed(() =>
  props.lensnodes.filter(
    (node) =>
      node.status === 'online' &&
      node.enrollment_status === 'approved' &&
      !node.token_revoked
  )
)

const selectedLensNode = computed(() =>
  props.lensnodes.find((node) => node.uuid === props.form.lensnode_uuid)
)

const workspaceRoot = computed(() =>
  String(selectedLensNode.value?.workspace_path || '/workspace').replace(
    /\/+$/,
    ''
  )
)

const workspacePrefix = computed(() => `${workspaceRoot.value}/`)

const targetPath = computed(() => {
  const relative = String(props.form.workspace_relative_path || '').trim()
  return relative ? `${workspacePrefix.value}${relative}` : workspacePrefix.value
})

const canCheckPath = computed(
  () => !!props.form.lensnode_uuid && !!props.form.workspace_relative_path
)

const canTestConnection = computed(() => {
  if (!props.form.lensnode_uuid) {
    return false
  }
  if (props.form.source_type === 'git') {
    if (!props.config.repo_url?.trim()) {
      return false
    }
    return (
      props.config.auth_scheme !== 'token' ||
      !!props.config.access_token?.trim() ||
      !!props.form.credential_configured
    )
  }
  return !!(
    props.config.document_url?.trim() ||
    props.config.app_token?.trim() ||
    props.config.doc_ids_text?.trim()
  )
})

const pathResultMessage = computed(() => {
  if (!props.pathResult) {
    return ''
  }
  const code = props.pathResult.message_code
  if (code) {
    const key = `lensAdmin.datasourceWizard.pathStatus.${code}`
    const translated = t(key)
    if (translated !== key) {
      return translated
    }
  }
  return props.pathResult.message || ''
})

const connectionResultMessage = computed(() => {
  if (!props.connectionResult) {
    return ''
  }
  const code = props.connectionResult.message_code
  if (code) {
    const key = `lensAdmin.datasourceWizard.connectionStatus.${code}`
    const translated = t(key)
    if (translated !== key) {
      return translated
    }
  }
  return props.connectionResult.message || ''
})

const canProceedWizard = computed(() => {
  if (wizardStep.value === 1) {
    return !!props.form.name?.trim() && !!props.form.source_type
  }
  if (wizardStep.value === 2) {
    return !!props.form.lensnode_uuid
  }
  if (wizardStep.value === 3) {
    if (props.form.source_type === 'git') {
      if (!props.config.repo_url?.trim()) {
        return false
      }
      return (
        props.config.auth_scheme !== 'token' ||
        !!props.config.access_token?.trim() ||
        !!props.form.credential_configured
      )
    }
    return !!(
      props.config.document_url?.trim() ||
      props.config.app_token?.trim() ||
      props.config.doc_ids_text?.trim()
    )
  }
  return !!props.form.workspace_relative_path?.trim()
})

function nextWizardStep() {
  if (wizardStep.value < WIZARD_STEP_COUNT) wizardStep.value++
}

function prevWizardStep() {
  if (wizardStep.value > 1) wizardStep.value--
}

watch(
  () => props.show,
  (show) => {
    if (show) {
      wizardStep.value = 1
    }
  }
)

watch(
  () => [
    props.form.lensnode_uuid,
    props.form.source_type,
    JSON.stringify(props.config || {})
  ],
  () => {
    emit('connection-change')
  }
)
</script>

<style scoped>
.form-input {
  @apply w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}
</style>
