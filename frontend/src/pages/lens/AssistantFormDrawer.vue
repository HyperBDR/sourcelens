<template>
  <BaseDrawer
    :show="show"
    :title="drawerTitle"
    :subtitle="drawerSubtitle"
    @close="$emit('close')"
  >
    <!-- Wizard step indicator -->
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
            <svg
              v-if="i + 1 < wizardStep"
              class="h-4 w-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2.5"
                d="M5 13l4 4L19 7"
              />
            </svg>
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

    <!-- Wizard Step 1 — Basics & Models -->
    <div v-if="wizardStep === 1" class="space-y-5">
      <p class="text-sm text-ink-500">{{ t('lensAdmin.wizard.step1Desc') }}</p>
      <FormRow :label="t('lensAdmin.fields.name')">
        <input v-model="form.name" class="form-input" required />
      </FormRow>
      <FormRow :label="t('lensAdmin.fields.description')">
        <textarea
          v-model="form.description"
          class="form-input min-h-24"
          :placeholder="t('lensAdmin.placeholders.assistantDescription')"
        />
        <p class="mt-1 text-xs text-ink-500">
          {{ t('lensAdmin.wizard.assistantDescriptionHint') }}
        </p>
      </FormRow>
      <FormRow :label="t('lensAdmin.fields.slug')">
        <input v-model="form.slug" class="form-input" required />
      </FormRow>
      <FormRow :label="t('lensAdmin.fields.agentModel') + ' *'">
        <select v-model="form.agent_model_ref" class="form-input" required>
          <option value="">
            {{ t('lensAdmin.placeholders.selectModel') }}
          </option>
          <option v-for="c in llmConfigOptions" :key="c.uuid" :value="c.uuid">
            {{ formatLLMConfigLabel(c) }}
          </option>
        </select>
        <p class="mt-1 text-xs text-ink-500">
          {{ t('lensAdmin.wizard.agentModelHint') }}
        </p>
      </FormRow>
      <FormRow :label="t('lensAdmin.fields.multimodalModel')">
        <select v-model="form.multimodal_model_ref" class="form-input">
          <option value="">{{ t('lensAdmin.placeholders.noModel') }}</option>
          <option v-for="c in llmConfigOptions" :key="c.uuid" :value="c.uuid">
            {{ formatLLMConfigLabel(c) }}
          </option>
        </select>
        <p class="mt-1 text-xs text-ink-500">
          {{ t('lensAdmin.wizard.multimodalModelHint') }}
        </p>
      </FormRow>
      <FormRow :label="t('lensAdmin.fields.maxConcurrency')">
        <input
          v-model.number="form.max_concurrency"
          type="number"
          min="1"
          max="50"
          class="form-input w-32"
        />
        <p class="mt-1 text-xs text-ink-500">
          {{ t('lensAdmin.wizard.maxConcurrencyHint') }}
        </p>
      </FormRow>
      <FormRow :label="t('lensAdmin.fields.agentRounds')">
        <div class="grid grid-cols-5 gap-2">
          <label
            v-for="tier in agentRoundsTiers"
            :key="tier.value"
            class="flex cursor-pointer flex-col items-center rounded-lg border-2 p-2 text-center transition-colors"
            :class="
              form.agent_rounds === tier.value
                ? 'border-brand-600 bg-brand-50 text-brand-700'
                : 'border-line bg-surface text-ink-600 hover:border-brand-300'
            "
          >
            <input
              type="radio"
              :value="tier.value"
              v-model="form.agent_rounds"
              class="sr-only"
            />
            <span class="text-sm font-medium">{{ tier.label }}</span>
            <span class="mt-0.5 text-xs opacity-60">{{ tier.hint }}</span>
          </label>
        </div>
      </FormRow>
    </div>

    <!-- Wizard Step 2 — Execution -->
    <div v-else-if="wizardStep === 2" class="space-y-4">
      <p class="text-sm text-ink-500">{{ t('lensAdmin.wizard.step2Desc') }}</p>
      <div class="grid gap-4 md:grid-cols-2">
        <FormRow :label="t('lensAdmin.fields.lensnode')">
          <select v-model="form.lensnode_uuid" class="form-input" required>
            <option value="">
              {{ t('lensAdmin.placeholders.selectLensNode') }}
            </option>
            <option v-for="ln in lensnodes" :key="ln.uuid" :value="ln.uuid">
              {{ ln.name }}
            </option>
          </select>
        </FormRow>
        <FormRow :label="t('lensAdmin.fields.type')">
          <select v-model="form.selected_task" class="form-input" required>
            <option value="">
              {{ t('lensAdmin.placeholders.selectType') }}
            </option>
            <option
              v-for="task in selectedLensNodeTasks"
              :key="task.name"
              :value="task.name"
              :title="task.description"
            >
              {{ formatAssistantType(task.name, t, task.title || task.name) }}
            </option>
          </select>
        </FormRow>
      </div>
      <div v-if="!isGeneralChatTask">
        <div class="mb-1 flex items-center justify-between">
          <span class="text-sm font-medium text-ink-700">{{
            t('lensAdmin.fields.selectedDirs')
          }}</span>
          <button
            v-if="form.lensnode_uuid"
            type="button"
            class="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-ink-500 transition-colors hover:bg-surface-sunken hover:text-ink-700 disabled:opacity-40"
            :disabled="refreshingDirs"
            @click="$emit('refresh-dirs')"
          >
            <svg
              class="h-3.5 w-3.5"
              :class="{ 'animate-spin': refreshingDirs }"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            {{ t('common.refresh') }}
          </button>
        </div>
        <select
          v-if="selectedLensNodeDirs.length"
          v-model="selectedDirPath"
          class="form-input font-mono"
        >
          <option value="">{{ t('lensAdmin.placeholders.selectDir') }}</option>
          <option
            v-for="dir in selectedLensNodeDirs"
            :key="dir.path"
            :value="dir.path"
          >
            {{ dir.path }}
          </option>
        </select>
        <div
          v-else
          class="rounded-md border border-line bg-surface-sunken p-3 text-sm text-ink-500"
        >
          {{ t('lensAdmin.placeholders.noDirs') }}
        </div>
        <div v-if="selectedDirPath" class="mt-2">
          <label class="mb-1 block text-xs font-medium text-ink-500">
            {{ t('lensAdmin.fields.includePaths') }}
          </label>
          <textarea
            class="form-input min-h-20 font-mono"
            :placeholder="t('lensAdmin.placeholders.includePaths')"
            :value="selectedDirScopeText(selectedDirPath)"
            @input="updateDirScope(selectedDirPath, $event.target.value)"
          />
        </div>
      </div>
      <div
        v-else
        class="rounded-md border border-primary-200 bg-primary-50 p-3 text-sm text-primary-700"
      >
        {{ t('lensAdmin.wizard.generalChatExecutionHint') }}
      </div>
      <FormRow
        v-if="!isGeneralChatTask"
        :label="t('lensAdmin.fields.retrievalPolicy')"
      >
        <div
          class="grid gap-3 rounded-md border border-line bg-surface-sunken p-3"
        >
          <label class="block text-xs font-medium text-ink-600">
            {{ t('lensAdmin.fields.excludeExtensions') }}
            <textarea
              v-model="form.exclude_extensions_text"
              class="form-input mt-1 min-h-28 font-mono"
              :placeholder="t('lensAdmin.placeholders.extensions')"
            />
          </label>
          <label class="block text-xs font-medium text-ink-600">
            {{ t('lensAdmin.fields.excludeDirs') }}
            <textarea
              v-model="form.exclude_dirs_text"
              class="form-input mt-1 min-h-28 font-mono"
              :placeholder="t('lensAdmin.placeholders.excludeDirs')"
            />
          </label>
        </div>
      </FormRow>
    </div>

    <!-- Wizard Step 3 — Workspace, Skills & MCP -->
    <div v-else-if="wizardStep === 3" class="space-y-5">
      <p class="text-sm text-ink-500">{{ t('lensAdmin.wizard.step3Desc') }}</p>
      <div v-if="!isGeneralChatTask">
        <span class="text-sm font-medium text-ink-700">{{
          t('lensAdmin.wizard.contextLabel')
        }}</span>
        <p class="mb-2 text-xs text-ink-500">
          {{ t('lensAdmin.wizard.contextHint') }}
        </p>
        <textarea
          v-model="form.workspace_guide_overview"
          class="form-input min-h-60"
          :placeholder="t('lensAdmin.wizard.contextPlaceholder')"
        />
      </div>
      <div>
        <div class="mb-2 text-sm font-medium text-ink-700">
          {{
            isGeneralChatTask
              ? t('lensAdmin.wizard.skillsSectionRequired')
              : t('lensAdmin.wizard.skillsSection')
          }}
        </div>
        <p v-if="isGeneralChatTask" class="mb-2 text-xs text-ink-500">
          {{ t('lensAdmin.wizard.generalChatSkillsHint') }}
        </p>
        <div
          v-if="selectableSkills.length"
          class="space-y-2 rounded-md border border-line bg-surface-sunken p-2"
        >
          <label
            v-for="skill in selectableSkills"
            :key="skill.uuid"
            class="group flex cursor-pointer items-start gap-3 rounded-md border bg-surface px-3 py-2.5 transition-colors hover:border-primary-200 hover:bg-primary-50/40"
            :class="
              isSkillSelected(skill.uuid)
                ? 'border-primary-300 bg-primary-50'
                : 'border-line'
            "
          >
            <input
              type="checkbox"
              :value="skill.uuid"
              v-model="form.skill_uuids"
              class="sr-only"
            />
            <span
              class="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded border transition-colors"
              :class="
                isSkillSelected(skill.uuid)
                  ? 'border-primary-600 bg-primary-600 text-white'
                  : 'border-line bg-surface text-transparent group-hover:border-primary-300'
              "
            >
              <svg
                class="h-3.5 w-3.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="3"
                  d="M5 13l4 4L19 7"
                />
              </svg>
            </span>
            <div class="min-w-0 flex-1 space-y-1">
              <div class="flex min-w-0 items-start justify-between gap-2">
                <div
                  class="min-w-0 truncate text-sm font-semibold text-ink-900"
                >
                  {{ skill.name }}
                </div>
                <StatusBadge :status="skill.enabled ? 'enabled' : 'disabled'" />
              </div>
              <div class="truncate font-mono text-xs text-ink-400">
                {{ skill.slug }}
              </div>
              <p
                v-if="skillDescription(skill)"
                class="line-clamp-2 text-xs leading-5 text-ink-500"
              >
                {{ skillDescription(skill) }}
              </p>
            </div>
          </label>
        </div>
        <div
          v-else
          class="rounded-md border border-line bg-surface-sunken p-3 text-sm text-ink-500"
        >
          {{ t('lensAdmin.wizard.noSkills') }}
        </div>
      </div>
      <div>
        <div class="mb-2 text-sm font-medium text-ink-700">
          {{ t('lensAdmin.wizard.mcpSection') }}
        </div>
        <div
          v-if="mcps.length"
          class="space-y-1 rounded-md border border-line bg-surface-sunken p-2"
        >
          <label
            v-for="mcp in mcps"
            :key="mcp.uuid"
            class="flex cursor-pointer items-center gap-3 rounded px-2 py-2 transition-colors hover:bg-surface"
          >
            <input
              type="checkbox"
              :value="mcp.uuid"
              v-model="form.mcp_uuids"
              class="h-4 w-4 flex-shrink-0 rounded border-line text-brand-600 focus:ring-brand-500"
            />
            <div class="min-w-0 flex-1">
              <div class="text-sm font-medium text-ink-900">{{ mcp.name }}</div>
              <div class="text-xs text-ink-400">
                {{ mcp.transport }} · {{ mcp.endpoint || emptyValue }}
              </div>
            </div>
            <StatusBadge :status="mcp.enabled ? 'enabled' : 'disabled'" />
          </label>
        </div>
        <div
          v-else
          class="rounded-md border border-line bg-surface-sunken p-3 text-sm text-ink-500"
        >
          {{ t('lensAdmin.wizard.noMcp') }}
        </div>
      </div>
    </div>

    <!-- Wizard Step 4 — Authorization -->
    <div v-else-if="wizardStep === 4" class="space-y-5">
      <p class="text-sm text-ink-500">{{ t('lensAdmin.wizard.step4Desc') }}</p>
      <FormRow :label="t('lensAdmin.fields.visibility')">
        <div class="grid grid-cols-2 gap-3">
          <label
            v-for="opt in ['public', 'private']"
            :key="opt"
            class="flex cursor-pointer items-start gap-3 rounded-lg border-2 p-3 transition-colors"
            :class="
              form.visibility === opt
                ? opt === 'private'
                  ? 'border-amber-400 bg-amber-50'
                  : 'border-emerald-400 bg-emerald-50'
                : 'border-line bg-surface hover:border-brand-300'
            "
          >
            <input
              type="radio"
              :value="opt"
              v-model="form.visibility"
              class="sr-only"
            />
            <component
              :is="opt === 'private' ? LockIcon : GlobeIcon"
              class="mt-0.5 h-5 w-5 flex-shrink-0"
              :class="
                form.visibility === opt
                  ? opt === 'private'
                    ? 'text-amber-600'
                    : 'text-emerald-600'
                  : 'text-ink-400'
              "
            />
            <div class="min-w-0">
              <div
                class="text-sm font-semibold"
                :class="
                  form.visibility === opt ? 'text-ink-900' : 'text-ink-600'
                "
              >
                {{ t(`lensAdmin.visibility.${opt}`) }}
              </div>
              <div class="mt-0.5 text-xs leading-5 text-ink-500">
                {{ t(`lensAdmin.visibility.${opt}Desc`) }}
              </div>
            </div>
          </label>
        </div>
        <p class="mt-2 text-xs text-ink-500">
          {{ t('lensAdmin.wizard.visibilityHint') }}
        </p>
      </FormRow>

      <div v-if="form.visibility === 'private'" class="space-y-4">
        <div
          class="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-700"
        >
          <LockIcon class="mt-0.5 h-4 w-4 flex-shrink-0" />
          <span>{{ t('lensAdmin.access.hint') }}</span>
        </div>
        <div class="grid gap-4 md:grid-cols-2">
          <div class="overflow-hidden rounded-lg border border-line">
            <div
              class="flex items-center justify-between border-b border-line bg-surface-sunken px-3 py-2"
            >
              <div
                class="flex items-center gap-2 text-sm font-medium text-ink-700"
              >
                <UsersIcon class="h-4 w-4 text-ink-400" />
                {{ t('lensAdmin.access.groups') }}
              </div>
              <span
                class="rounded-full bg-surface px-2 py-0.5 text-xs font-medium text-ink-500"
              >
                {{ form.access_group_ids.length }}
              </span>
            </div>
            <div
              v-if="groups.length"
              class="max-h-52 space-y-1 overflow-y-auto p-2"
            >
              <label
                v-for="g in groups"
                :key="g.id"
                class="flex cursor-pointer items-center gap-2.5 rounded-md border px-2.5 py-2 text-sm transition-colors"
                :class="
                  form.access_group_ids.includes(g.id)
                    ? 'border-brand-300 bg-brand-50 text-ink-900'
                    : 'border-transparent text-ink-700 hover:bg-surface-sunken'
                "
              >
                <input
                  type="checkbox"
                  :value="g.id"
                  v-model="form.access_group_ids"
                  class="h-4 w-4 flex-shrink-0 rounded border-line text-brand-600 focus:ring-brand-500"
                />
                <UsersIcon class="h-4 w-4 flex-shrink-0 text-ink-400" />
                <span class="truncate">{{ g.name }}</span>
              </label>
            </div>
            <p v-else class="px-3 py-8 text-center text-xs text-ink-400">
              {{ t('lensAdmin.access.noGroups') }}
            </p>
          </div>

          <div class="overflow-hidden rounded-lg border border-line">
            <div
              class="flex items-center justify-between border-b border-line bg-surface-sunken px-3 py-2"
            >
              <div
                class="flex items-center gap-2 text-sm font-medium text-ink-700"
              >
                <UserIcon class="h-4 w-4 text-ink-400" />
                {{ t('lensAdmin.access.users') }}
              </div>
              <span
                class="rounded-full bg-surface px-2 py-0.5 text-xs font-medium text-ink-500"
              >
                {{ form.access_user_ids.length }}
              </span>
            </div>
            <div
              v-if="selectableUsers.length"
              class="max-h-52 space-y-1 overflow-y-auto p-2"
            >
              <label
                v-for="u in selectableUsers"
                :key="u.id"
                class="flex cursor-pointer items-center gap-2.5 rounded-md border px-2.5 py-2 text-sm transition-colors"
                :class="
                  form.access_user_ids.includes(u.id)
                    ? 'border-brand-300 bg-brand-50'
                    : 'border-transparent hover:bg-surface-sunken'
                "
              >
                <input
                  type="checkbox"
                  :value="u.id"
                  v-model="form.access_user_ids"
                  class="h-4 w-4 flex-shrink-0 rounded border-line text-brand-600 focus:ring-brand-500"
                />
                <span
                  class="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-brand-100 text-xs font-semibold text-brand-700"
                >
                  {{ userInitial(u) }}
                </span>
                <div class="min-w-0 flex-1">
                  <div class="truncate text-ink-900">{{ userLabel(u) }}</div>
                  <div v-if="u.email" class="truncate text-xs text-ink-400">
                    {{ u.email }}
                  </div>
                </div>
              </label>
            </div>
            <p v-else class="px-3 py-8 text-center text-xs text-ink-400">
              {{ t('lensAdmin.access.noUsers') }}
            </p>
          </div>
        </div>
      </div>
    </div>

    <p v-if="formError" class="mt-4 text-sm text-danger-700">{{ formError }}</p>

    <template #footer>
      <div class="flex items-center justify-between">
        <BaseButton
          variant="outline"
          @click="wizardStep > 1 ? prevWizardStep() : $emit('close')"
        >
          {{ wizardStep > 1 ? t('lensAdmin.wizard.back') : t('common.cancel') }}
        </BaseButton>
        <div class="flex items-center gap-3">
          <span class="text-xs text-ink-400"
            >{{ wizardStep }} / {{ WIZARD_STEP_COUNT }}</span
          >
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
            @click="$emit('save')"
          >
            {{
              mode === 'create'
                ? t('lensAdmin.wizard.finish')
                : t('common.save')
            }}
          </BaseButton>
        </div>
      </div>
    </template>
  </BaseDrawer>
</template>

<script setup>
import {
  Globe as GlobeIcon,
  Lock as LockIcon,
  User as UserIcon,
  Users as UsersIcon
} from '@lucide/vue'
import { computed, defineComponent, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'

import {
  EMPTY_VALUE,
  formatAssistantType,
  formatLLMConfigLabel
} from './adminHelpers'

const props = defineProps({
  show: Boolean,
  mode: { type: String, default: 'create' },
  // Shared reactive form object owned by the parent; this drawer writes into
  // it directly so the parent's save() can read the result unchanged.
  form: { type: Object, required: true },
  lensnodes: { type: Array, default: () => [] },
  skills: { type: Array, default: () => [] },
  mcps: { type: Array, default: () => [] },
  llmConfigOptions: { type: Array, default: () => [] },
  groups: { type: Array, default: () => [] },
  users: { type: Array, default: () => [] },
  saving: Boolean,
  formError: { type: String, default: '' },
  refreshingDirs: Boolean
})

defineEmits(['close', 'save', 'refresh-dirs'])

const { t } = useI18n()

const emptyValue = EMPTY_VALUE
const WIZARD_STEP_COUNT = 4
const wizardStep = ref(1)

watch(
  () => props.show,
  (show) => {
    if (show) {
      wizardStep.value = 1
    }
  }
)

const FormRow = defineComponent({
  props: {
    label: {
      type: String,
      required: true
    }
  },
  setup(rowProps, { slots }) {
    return () =>
      h('div', [
        h(
          'label',
          { class: 'mb-1 block text-sm font-medium text-ink-700' },
          rowProps.label
        ),
        slots.default?.()
      ])
  }
})

const drawerTitle = computed(() =>
  props.mode === 'create'
    ? t('lensAdmin.drawer.createTitle')
    : t('lensAdmin.drawer.editTitle')
)

const drawerSubtitle = computed(() =>
  props.mode === 'edit' ? props.form.name || '' : ''
)

const agentRoundsTiers = computed(() => [
  {
    value: 'flash',
    label: t('lensAdmin.agentRounds.flash'),
    hint: t('lensAdmin.agentRounds.flashHint')
  },
  {
    value: 'fast',
    label: t('lensAdmin.agentRounds.fast'),
    hint: t('lensAdmin.agentRounds.fastHint')
  },
  {
    value: 'balanced',
    label: t('lensAdmin.agentRounds.balanced'),
    hint: t('lensAdmin.agentRounds.balancedHint')
  },
  {
    value: 'deep',
    label: t('lensAdmin.agentRounds.deep'),
    hint: t('lensAdmin.agentRounds.deepHint')
  },
  {
    value: 'max',
    label: t('lensAdmin.agentRounds.max'),
    hint: t('lensAdmin.agentRounds.maxHint')
  }
])

const wizardStepsMeta = computed(() => [
  { key: 'basic', title: t('lensAdmin.wizard.step1Title') },
  { key: 'execution', title: t('lensAdmin.wizard.step2Title') },
  { key: 'tools', title: t('lensAdmin.wizard.step3Title') },
  { key: 'access', title: t('lensAdmin.wizard.step4Title') }
])

const canProceedWizard = computed(() => {
  if (wizardStep.value === 1) {
    return (
      !!props.form.name?.trim() &&
      !!props.form.slug?.trim() &&
      !!props.form.agent_model_ref
    )
  }
  if (wizardStep.value === 2) {
    if (isGeneralChatTask.value) {
      return !!props.form.lensnode_uuid && !!props.form.selected_task
    }
    return (
      !!props.form.lensnode_uuid &&
      !!props.form.selected_task &&
      selectedDirs().length > 0
    )
  }
  if (wizardStep.value === 3 && isGeneralChatTask.value) {
    return (props.form.skill_uuids || []).length > 0
  }
  return true
})

const isGeneralChatTask = computed(
  () => props.form.selected_task === 'general_chat'
)

const selectedLensNodeTasks = computed(() => {
  const selected = props.lensnodes.find(
    (lensnode) => lensnode.uuid === props.form.lensnode_uuid
  )
  return Array.isArray(selected?.tasks) ? selected.tasks : []
})

const selectedLensNodeDirs = computed(() => {
  const selected = props.lensnodes.find(
    (lensnode) => lensnode.uuid === props.form.lensnode_uuid
  )
  const dirs = Array.isArray(selected?.available_dirs)
    ? selected.available_dirs
    : []
  return dirs
    .map((dir) => {
      if (typeof dir === 'string') {
        return { path: dir }
      }
      return { ...dir, path: dir.path || dir.name || '' }
    })
    .filter((dir) => dir.path)
})

function nextWizardStep() {
  if (wizardStep.value < WIZARD_STEP_COUNT) wizardStep.value++
}

function prevWizardStep() {
  if (wizardStep.value > 1) wizardStep.value--
}

function userLabel(user) {
  return user.display_name || user.username || user.email || `#${user.id}`
}

function userInitial(user) {
  return (userLabel(user).trim()[0] || '?').toUpperCase()
}

const selectableUsers = computed(() =>
  props.users.filter((user) => !user.is_staff && !user.is_superuser)
)

const selectableSkills = computed(() =>
  props.skills.filter(
    (skill) =>
      !(
        typeof skill.slug === 'string' &&
        skill.slug.endsWith('-workspace-guide')
      )
  )
)

function isSkillSelected(uuid) {
  return (props.form.skill_uuids || []).includes(uuid)
}

function skillDescription(skill) {
  const definition = skill?.definition || {}
  return (
    skill?.description ||
    definition.description ||
    definition.summary ||
    skill?.package_manifest?.description ||
    ''
  )
}

function selectedDirs() {
  return Array.isArray(props.form.selected_dirs) ? props.form.selected_dirs : []
}

const selectedDirPath = computed({
  get() {
    return selectedDirs()[0]?.path || ''
  },
  set(path) {
    if (!path) {
      props.form.selected_dirs = []
      return
    }
    const existing = selectedDirs().find((dir) => dir.path === path)
    props.form.selected_dirs = [existing || { path, include_paths_text: '' }]
  }
})

function selectedDirScopeText(path) {
  const dir = selectedDirs().find((item) => item.path === path)
  return dir?.include_paths_text || ''
}

function updateDirScope(path, value) {
  props.form.selected_dirs = selectedDirs().map((dir) =>
    dir.path === path ? { ...dir, include_paths_text: value } : dir
  )
}

watch(
  () => props.form.lensnode_uuid,
  () => {
    if (
      props.show &&
      !selectedLensNodeTasks.value.some(
        (task) => task.name === props.form.selected_task
      )
    ) {
      props.form.selected_task = ''
    }
    ensureSelectedTask()
  }
)

watch(
  () => props.form.selected_task,
  () => {
    if (isGeneralChatTask.value) {
      props.form.selected_dirs = []
    }
  }
)

function ensureSelectedTask() {
  if (!props.show || props.form.selected_task) {
    return
  }
  props.form.selected_task = selectedLensNodeTasks.value[0]?.name || ''
}
</script>

<style scoped>
.form-input {
  @apply w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}
</style>
