<template>
  <div class="space-y-2">
    <div
      v-if="missingLabels.length"
      class="rounded-md border border-warning-200 bg-warning-50 px-3 py-2 text-xs text-warning-700"
    >
      {{ t('lensAdmin.compose.missingHint') }}
      <ul class="mt-1 list-disc pl-4">
        <li v-for="label in missingLabels" :key="label">{{ label }}</li>
      </ul>
    </div>

    <p class="text-xs text-ink-500">
      {{ t('lensAdmin.compose.tokenOnce') }}
    </p>

    <div class="relative">
      <div class="absolute right-1.5 top-1.5 flex items-center gap-1">
        <button
          type="button"
          :title="
            copied ? t('lensAdmin.compose.copied') : t('lensAdmin.compose.copy')
          "
          class="rounded-md p-1.5 text-ink-300 transition-colors hover:bg-white/10 hover:text-white"
          @click="copy"
        >
          <Check
            v-if="copied"
            :size="16"
            :stroke-width="2"
            class="text-success-400"
          />
          <Copy v-else :size="16" :stroke-width="2" />
        </button>
        <button
          type="button"
          :title="t('lensAdmin.compose.download')"
          class="rounded-md p-1.5 text-ink-300 transition-colors hover:bg-white/10 hover:text-white"
          @click="download"
        >
          <Download :size="16" :stroke-width="2" />
        </button>
      </div>
      <pre
        class="max-h-80 overflow-auto rounded-md border border-line bg-ink-900 p-3 font-mono text-xs leading-relaxed text-ink-100"
        >{{ composeText }}</pre
      >
    </div>

    <p class="text-xs text-ink-400">
      {{ t('lensAdmin.compose.volumeHint') }}
    </p>
  </div>
</template>

<script setup>
import { Check, Copy, Download } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { useComposeClipboard } from './useComposeClipboard'

const props = defineProps({
  composeText: {
    type: String,
    required: true
  },
  fileName: {
    type: String,
    default: 'docker-compose.yml'
  },
  // Translated labels of settings still missing, shown as a warning.
  missingLabels: {
    type: Array,
    default: () => []
  }
})

const { t } = useI18n()
const { copied, copy, download } = useComposeClipboard(
  () => props.composeText,
  { fileName: props.fileName }
)
</script>
