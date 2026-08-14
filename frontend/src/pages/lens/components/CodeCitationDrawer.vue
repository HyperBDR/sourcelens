<template>
  <BaseDrawer
    :show="show"
    :title="t('lens.chat.citations.viewerTitle')"
    :subtitle="citation?.path || ''"
    width="2xl"
    @close="$emit('close')"
  >
    <BaseLoading v-if="loading" :message="t('lens.chat.citations.loading')" />

    <div v-else-if="error" class="citation-error" role="alert">
      <AlertCircle :size="24" aria-hidden="true" />
      <p>{{ error }}</p>
      <BaseButton variant="outline" size="sm" @click="$emit('retry')">
        {{ t('lens.chat.citations.retry') }}
      </BaseButton>
    </div>

    <div v-else-if="citation" class="citation-viewer">
      <dl class="citation-meta">
        <div>
          <dt>{{ t('lens.chat.citations.revision') }}</dt>
          <dd>{{ citation.revision }}</dd>
        </div>
        <div v-if="citation.symbol">
          <dt>{{ t('lens.chat.citations.symbol') }}</dt>
          <dd>{{ citation.symbol }}</dd>
        </div>
        <div>
          <dt>{{ t('lens.chat.citations.lines') }}</dt>
          <dd>
            {{ citation.highlight_start_line }}–{{
              citation.highlight_end_line
            }}
          </dd>
        </div>
      </dl>

      <p v-if="citation.supports" class="citation-supports">
        {{ citation.supports }}
      </p>

      <div class="citation-code" tabindex="0">
        <div
          v-for="line in citation.lines"
          :key="line.number"
          class="citation-code-line"
          :class="{
            'citation-code-line-highlighted': isHighlighted(line.number)
          }"
        >
          <span class="citation-line-number" aria-hidden="true">
            {{ line.number }}
          </span>
          <code>{{ line.content || ' ' }}</code>
        </div>
      </div>
    </div>
  </BaseDrawer>
</template>

<script setup>
import { AlertCircle } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'

const props = defineProps({
  show: { type: Boolean, default: false },
  citation: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' }
})

defineEmits(['close', 'retry'])

const { t } = useI18n()

function isHighlighted(lineNumber) {
  if (!props.citation) return false
  return (
    lineNumber >= props.citation.highlight_start_line &&
    lineNumber <= props.citation.highlight_end_line
  )
}
</script>

<style scoped>
.citation-error {
  @apply flex min-h-48 flex-col items-center justify-center gap-3 rounded-lg border border-line bg-surface-sunken p-6 text-center text-sm text-theme-muted;
}

.citation-viewer {
  @apply space-y-4;
}

.citation-meta {
  @apply flex flex-wrap gap-x-6 gap-y-3 rounded-lg border border-line bg-surface-sunken px-4 py-3;
}

.citation-meta dt {
  @apply text-xs text-theme-subtle;
}

.citation-meta dd {
  @apply mt-0.5 break-all font-mono text-xs font-medium text-theme;
}

.citation-supports {
  @apply text-sm leading-6 text-theme-secondary;
}

.citation-code {
  @apply max-h-[70vh] overflow-auto rounded-lg border border-line py-2 font-mono text-xs outline-none focus-visible:ring-2 focus-visible:ring-primary-500;
  color: var(--sl-code-text);
  background: var(--sl-code-bg);
}

.citation-code-line {
  @apply flex min-w-max border-l-2 border-transparent pr-4 leading-6;
}

.citation-code-line-highlighted {
  @apply border-primary-400;
  background: var(--sl-code-highlight);
}

.citation-line-number {
  @apply mr-4 w-14 flex-shrink-0 select-none text-right;
  color: var(--sl-code-line-number);
}

.citation-code code {
  @apply whitespace-pre;
}
</style>
