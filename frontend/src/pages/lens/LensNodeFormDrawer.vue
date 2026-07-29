<template>
  <BaseDrawer
    :show="show"
    :title="title"
    :subtitle="mode === 'edit' ? node?.name || '' : ''"
    @close="$emit('close')"
  >
    <div class="space-y-5">
      <!-- Name -->
      <div>
        <label class="mb-1 block text-sm font-medium text-ink-700">
          {{ t('lensAdmin.nodeForm.nameLabel') }}
        </label>
        <input
          v-model="name"
          class="form-input"
          :disabled="creating"
          required
          @change="onNameChange"
          @keyup.enter="onNameChange"
        />
        <p class="mt-1 text-xs text-ink-500">
          {{ t('lensAdmin.nodeForm.nameHint') }}
        </p>
      </div>

      <!-- Create mode: mount path + ready-to-run compose -->
      <template v-if="mode === 'create'">
        <div>
          <label class="mb-1 block text-sm font-medium text-ink-700">
            {{ t('lensAdmin.nodeForm.mountLabel') }}
          </label>
          <input v-model="workspacePath" class="form-input" />
          <p class="mt-1 text-xs text-ink-500">
            {{ t('lensAdmin.nodeForm.mountHint') }}
          </p>
        </div>

        <div
          v-if="missingLabels.length"
          class="rounded-md border border-warning-200 bg-warning-50 px-3 py-2 text-xs text-warning-700"
        >
          {{ t('lensAdmin.compose.missingHint') }}
          <ul class="mt-1 list-disc pl-4">
            <li v-for="label in missingLabels" :key="label">{{ label }}</li>
          </ul>
        </div>

        <div>
          <div class="mb-1 flex items-center justify-between">
            <span class="text-sm font-medium text-ink-700">
              docker-compose.yml
            </span>
            <div class="flex items-center gap-1">
              <button
                type="button"
                :title="
                  copied
                    ? t('lensAdmin.compose.copied')
                    : t('lensAdmin.compose.copy')
                "
                class="rounded-md p-1.5 text-ink-400 transition-colors hover:bg-surface-sunken hover:text-primary-600"
                @click="copyCompose"
              >
                <Check
                  v-if="copied"
                  :size="16"
                  :stroke-width="2"
                  class="text-success-600"
                />
                <Copy v-else :size="16" :stroke-width="2" />
              </button>
              <button
                type="button"
                :title="t('lensAdmin.compose.download')"
                class="rounded-md p-1.5 text-ink-400 transition-colors hover:bg-surface-sunken hover:text-primary-600"
                @click="downloadCompose"
              >
                <Download :size="16" :stroke-width="2" />
              </button>
            </div>
          </div>
          <Transition name="compose-fade" mode="out-in">
            <div
              v-if="creating"
              key="loading"
              class="flex items-center justify-center gap-2 rounded-md border border-line bg-ink-900 p-6 text-xs text-ink-300"
            >
              <svg
                class="h-4 w-4 animate-spin"
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
              {{ t('lensAdmin.nodeForm.issuing') }}
            </div>
            <pre
              v-else
              key="compose"
              class="max-h-96 overflow-auto rounded-md border border-line bg-ink-900 p-3 font-mono text-xs leading-relaxed text-ink-100"
              >{{ composeText }}</pre>
          </Transition>
        </div>

        <p class="text-xs text-ink-500">
          {{ t('lensAdmin.nodeForm.settingsHint') }}
          <router-link
            to="/management/lens/settings"
            class="text-primary-600 hover:underline"
            @click="$emit('close')"
          >
            {{ t('lensAdmin.nodeForm.settingsLink') }}
          </router-link>
        </p>

        <p
          v-if="created"
          class="rounded-md border border-success-200 bg-success-50 px-3 py-2 text-sm text-success-700"
        >
          {{ t('lensAdmin.nodeForm.createdBanner') }}
        </p>
        <p v-else class="text-xs text-ink-400">
          {{ t('lensAdmin.nodeForm.createHint') }}
        </p>
      </template>

      <p v-if="formError" class="text-sm text-danger-700">
        {{ formError }}
      </p>
    </div>

    <template #footer>
      <div class="flex items-center justify-between">
        <BaseButton variant="outline" @click="$emit('close')">
          {{
            created || mode === 'create'
              ? t('lensAdmin.nodeForm.finish')
              : t('common.cancel')
          }}
        </BaseButton>
        <BaseButton
          v-if="mode === 'create' && !created"
          variant="primary"
          :loading="creating"
          @click="createNode"
        >
          {{ t('lensAdmin.nodeForm.create') }}
        </BaseButton>
        <BaseButton
          v-else-if="mode === 'edit'"
          variant="primary"
          :loading="saving"
          @click="submitEdit"
        >
          {{ t('common.save') }}
        </BaseButton>
      </div>
    </template>
  </BaseDrawer>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { Check, Copy, Download } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { createLensNode, updateLensNode } from '@/api/lens'
import { extractErrorMessage } from '@/utils/api'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'

import { buildLensNodeCompose, lensNodeComposeSettings } from './adminHelpers'
import { useComposeClipboard } from './useComposeClipboard'

const DEFAULT_NODE_NAME = 'lensnode'

const props = defineProps({
  show: Boolean,
  mode: {
    type: String,
    default: 'create'
  },
  node: {
    type: Object,
    default: null
  },
  // Loaded global settings list (for compose image / server url).
  settings: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['close', 'done'])

const { t } = useI18n()
const { showSuccess, showError } = useToast()

const name = ref(DEFAULT_NODE_NAME)
const workspacePath = ref('/workspace')
const creating = ref(false)
const saving = ref(false)
const formError = ref('')
const created = ref(null)

const title = computed(() =>
  props.mode === 'edit'
    ? t('lensAdmin.nodeForm.editTitle')
    : t('lensAdmin.nodeForm.createTitle')
)

const composeConfig = computed(() => lensNodeComposeSettings(props.settings))

const missingLabels = computed(() => {
  const config = composeConfig.value
  return config.serverUrl ? [] : [t('lensAdmin.settings.publicBaseUrlTitle')]
})

const composeText = computed(() =>
  buildLensNodeCompose({
    name: name.value || DEFAULT_NODE_NAME,
    token: created.value?.token || t('lensAdmin.nodeForm.tokenPlaceholder'),
    hostPath: workspacePath.value || '/workspace',
    ...composeConfig.value
  })
)

// Create the node once and issue a real token. After this the compose holds a
// usable token and can be copied/downloaded repeatedly within this drawer.
async function createNode() {
  if (creating.value || created.value) return
  if (!name.value.trim()) {
    formError.value = t('management.usernameRequired')
    return
  }
  creating.value = true
  formError.value = ''
  try {
    created.value = await createLensNode({ name: name.value.trim() })
    emit('done')
  } catch (error) {
    formError.value = extractErrorMessage(
      error,
      t('lensAdmin.messages.saveFailed')
    )
    showError(formError.value)
  } finally {
    creating.value = false
  }
}

async function ensureCreated() {
  if (created.value) return true
  await createNode()
  return !!created.value
}

// Keep the backend node name in sync when the user renames after creation.
async function onNameChange() {
  if (props.mode !== 'create' || !created.value) return
  const newName = name.value.trim()
  if (!newName || newName === created.value.name) return
  try {
    await updateLensNode(created.value.uuid, { name: newName })
    created.value.name = newName
    emit('done')
  } catch (error) {
    showError(extractErrorMessage(error, t('lensAdmin.messages.saveFailed')))
  }
}

async function submitEdit() {
  if (!name.value.trim()) {
    formError.value = t('management.usernameRequired')
    return
  }
  saving.value = true
  formError.value = ''
  try {
    await updateLensNode(props.node.uuid, { name: name.value.trim() })
    showSuccess(t('lensAdmin.messages.saveSuccess'))
    emit('done')
    emit('close')
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

const {
  copied,
  copy: copyCompose,
  download: downloadCompose
} = useComposeClipboard(() => composeText.value, { before: ensureCreated })

watch(
  () => props.show,
  (show) => {
    if (show) {
      name.value =
        props.mode === 'edit' ? props.node?.name || '' : DEFAULT_NODE_NAME
      workspacePath.value = '/workspace'
      created.value = null
      formError.value = ''
      copied.value = false
    }
  }
)
</script>

<style scoped>
.form-input {
  @apply w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}

.compose-fade-enter-active,
.compose-fade-leave-active {
  transition: opacity 0.25s ease;
}

.compose-fade-enter-from,
.compose-fade-leave-to {
  opacity: 0;
}
</style>
