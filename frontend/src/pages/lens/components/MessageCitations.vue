<template>
  <details v-if="citations.length" class="message-citations">
    <summary class="message-citations-summary">
      <BookOpen :size="16" aria-hidden="true" />
      <span>{{ t('lens.chat.citations.title') }}</span>
      <span class="message-citations-count">
        {{ t('lens.chat.citations.count', { count: citations.length }) }}
      </span>
      <ChevronDown
        :size="16"
        class="message-citations-chevron"
        aria-hidden="true"
      />
    </summary>
    <div class="message-citations-list">
      <button
        v-for="citation in citations"
        :key="citation.id"
        type="button"
        class="message-citation"
        :aria-label="
          t('lens.chat.citations.open', {
            location: citationLocation(citation)
          })
        "
        @click="$emit('open', citation)"
      >
        <Code2 :size="17" class="message-citation-icon" aria-hidden="true" />
        <span class="message-citation-body">
          <span class="message-citation-location">
            {{ citationLocation(citation) }}
          </span>
          <span v-if="citation.symbol" class="message-citation-symbol">
            {{ citation.symbol }}
          </span>
          <span v-if="citation.supports" class="message-citation-supports">
            {{ citation.supports }}
          </span>
        </span>
        <ExternalLink :size="15" aria-hidden="true" />
      </button>
    </div>
  </details>
</template>

<script setup>
import { BookOpen, ChevronDown, Code2, ExternalLink } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import { citationLocation } from '@/pages/lens/codeCitations'

defineProps({
  citations: { type: Array, default: () => [] }
})

defineEmits(['open'])

const { t } = useI18n()
</script>

<style scoped>
.message-citations {
  @apply mt-4 border-t border-line pt-3;
}

.message-citations-summary {
  @apply flex cursor-pointer list-none items-center gap-2 rounded-md px-1 py-1.5 text-sm font-medium text-theme-secondary outline-none transition-colors hover:text-theme focus-visible:ring-2 focus-visible:ring-primary-500;
}

.message-citations-summary::-webkit-details-marker {
  display: none;
}

.message-citations-count {
  @apply text-xs font-normal text-theme-subtle;
}

.message-citations-chevron {
  @apply ml-auto transition-transform;
}

.message-citations[open] .message-citations-chevron {
  transform: rotate(180deg);
}

.message-citations-list {
  @apply mt-2 space-y-2;
}

.message-citation {
  @apply flex w-full items-start gap-3 rounded-lg border border-line bg-surface px-3 py-2.5 text-left text-theme-secondary transition-colors hover:border-line-strong hover:bg-surface-sunken focus:outline-none focus-visible:ring-2 focus-visible:ring-primary-500;
}

.message-citation-icon {
  @apply mt-0.5 flex-shrink-0 text-primary-600;
}

.message-citation-body {
  @apply min-w-0 flex-1;
}

.message-citation-location {
  @apply block break-all font-mono text-xs font-medium text-theme;
}

.message-citation-symbol,
.message-citation-supports {
  @apply mt-1 block text-xs text-theme-muted;
}

.message-citation-symbol {
  @apply break-all font-mono;
}
</style>
