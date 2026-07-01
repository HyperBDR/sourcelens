<template>
  <BaseModal :show="open" :title="t('lens.qa.shareTitle')" @close="emitClose">
    <div class="space-y-4">
      <p class="rounded-md bg-warning/10 px-3 py-2 text-xs text-warning">
        {{ t('lens.qa.shareWarning') }}
      </p>

      <div>
        <label class="mb-1 block text-xs font-medium text-ink-500">
          {{ t('lens.qa.shareTitleLabel') }}
        </label>
        <input
          v-model="title"
          type="text"
          class="w-full rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-800 focus:border-primary-500 focus:outline-none"
        />
      </div>

      <div v-if="answerPreview">
        <div class="mb-1 text-xs font-medium text-ink-500">
          {{ t('lens.qa.previewLabel') }}
        </div>
        <p
          class="line-clamp-3 rounded-md border border-line bg-surface-sunken px-3 py-2 text-xs text-ink-500"
        >
          {{ answerPreview }}
        </p>
      </div>

      <div v-if="share">
        <label class="mb-1 block text-xs font-medium text-ink-500">
          {{ t('lens.qa.linkLabel') }}
        </label>
        <div class="flex items-center gap-2">
          <a
            :href="shareLink"
            target="_blank"
            rel="noopener"
            class="min-w-0 flex-1 truncate font-mono text-xs text-ink-500 no-underline transition-colors hover:text-primary-600 hover:underline"
            :title="shareLink"
          >
            {{ shareLink }}
          </a>
          <button
            type="button"
            class="shrink-0 rounded-md p-1.5 text-ink-400 transition-colors hover:bg-surface-sunken hover:text-primary-600"
            :title="t('lens.share.copyLink')"
            @click="copy"
          >
            <Copy :size="15" :stroke-width="2" aria-hidden="true" />
          </button>
        </div>
        <p class="mt-2 text-xs text-ink-400">{{ t('lens.qa.listNote') }}</p>
      </div>
    </div>

    <template #footer>
      <div class="flex justify-end gap-2">
        <BaseButton v-if="share" variant="danger" size="sm" @click="unshare">
          {{ t('lens.qa.unshare') }}
        </BaseButton>
        <BaseButton
          variant="primary"
          size="sm"
          :loading="creating || saving"
          @click="primaryAction"
        >
          {{ primaryLabel }}
        </BaseButton>
      </div>
    </template>
  </BaseModal>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Copy } from '@lucide/vue'

import BaseModal from '@/components/ui/BaseModal.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import { shareRun, updateMyShare, deleteShare } from '@/api/lens'
import { copyToClipboard } from '@/utils/clipboard'
import { qaShareUrl } from '@/utils/lens'
import { useToast } from '@/composables/useToast'

const props = defineProps({
  open: { type: Boolean, default: false },
  runUuid: { type: String, default: '' },
  existingShare: { type: Object, default: null },
  question: { type: String, default: '' },
  answerPreview: { type: String, default: '' }
})
const emit = defineEmits(['close', 'shared', 'unshared'])

function defaultTitle(question) {
  return (question || '').replace(/\s+/g, ' ').trim().slice(0, 80)
}

const { t } = useI18n()
const { showSuccess, showError } = useToast()

const title = ref('')
const share = ref(null)
const creating = ref(false)
const saving = ref(false)

const shareLink = computed(() =>
  share.value ? qaShareUrl(share.value.token) : ''
)

const titleDirty = computed(
  () => !!share.value && title.value.trim() !== (share.value.title || '')
)

const primaryLabel = computed(() => {
  if (!share.value) {
    return t('lens.qa.createLink')
  }
  return titleDirty.value ? t('lens.qa.saveTitle') : t('lens.qa.done')
})

watch(
  () => props.open,
  (open) => {
    if (open) {
      share.value = props.existingShare || null
      title.value = share.value?.title || defaultTitle(props.question)
      creating.value = false
      saving.value = false
    }
  }
)

function emitClose() {
  emit('close')
}

function primaryAction() {
  if (!share.value) {
    return create()
  }
  if (titleDirty.value) {
    return saveTitle()
  }
  return emitClose()
}

async function create() {
  if (!props.runUuid) {
    return
  }
  creating.value = true
  try {
    share.value = await shareRun(props.runUuid, { title: title.value.trim() })
    title.value = share.value.title || ''
    emit('shared', share.value)
    showSuccess(t('lens.qa.shared'))
  } catch {
    showError(t('lens.qa.shareFailed'))
  } finally {
    creating.value = false
  }
}

async function saveTitle() {
  if (!share.value) {
    return
  }
  saving.value = true
  try {
    share.value = await updateMyShare(share.value.uuid, {
      title: title.value.trim()
    })
    title.value = share.value.title || ''
    showSuccess(t('lens.qa.actionDone'))
  } catch {
    showError(t('lens.qa.shareFailed'))
  } finally {
    saving.value = false
  }
}

async function copy() {
  if (await copyToClipboard(shareLink.value)) {
    showSuccess(t('lens.qa.copied'))
  } else {
    showError(t('lens.qa.copyFailed'))
  }
}

async function unshare() {
  if (!share.value) {
    return
  }
  try {
    await deleteShare(share.value.uuid)
    showSuccess(t('lens.qa.unshared'))
    emit('unshared', share.value)
    share.value = null
    emitClose()
  } catch {
    showError(t('lens.qa.shareFailed'))
  }
}
</script>
