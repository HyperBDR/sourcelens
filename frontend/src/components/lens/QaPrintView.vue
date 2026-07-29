<template>
  <article class="qa-print-view">
    <header class="qa-print-header">
      <div class="qa-print-brand">
        SourceLens · {{ t('lens.qa.agentBadge') }}
      </div>
      <h1>{{ title || question }}</h1>
      <p v-if="assistantName" class="qa-print-agent">
        {{ t('lens.qa.agentAnswerBy', { name: assistantName }) }}
      </p>
      <p v-if="publishedAt" class="qa-print-date">
        {{ formatDate(publishedAt, 'yyyy-MM-dd HH:mm') }}
      </p>
    </header>

    <section class="qa-print-question">
      <h2>{{ t('lens.qa.question') }}</h2>
      <p>{{ question }}</p>
      <div v-if="inputAttachments.length" class="qa-print-files">
        <h3>{{ t('lens.qa.inputAttachments') }}</h3>
        <ul>
          <li
            v-for="file in inputAttachments"
            :key="file.uuid || fileName(file)"
          >
            {{ fileName(file) }}
          </li>
        </ul>
      </div>
    </section>

    <section class="qa-print-answer">
      <h2>{{ t('lens.qa.answer') }}</h2>
      <MarkdownRenderer :content="answer" />
      <div v-if="outputFiles.length" class="qa-print-files">
        <h3>{{ t('lens.qa.outputFiles') }}</h3>
        <ul>
          <li v-for="file in outputFiles" :key="file.uuid || fileName(file)">
            {{ fileName(file) }}
          </li>
        </ul>
      </div>
    </section>

    <footer>{{ t('lens.qa.exportFooter') }}</footer>
  </article>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

import MarkdownRenderer from '@/components/ui/MarkdownRenderer.vue'
import { formatDate } from '@/utils/formatting'

defineProps({
  title: { type: String, default: '' },
  question: { type: String, default: '' },
  answer: { type: String, default: '' },
  assistantName: { type: String, default: '' },
  publishedAt: { type: String, default: '' },
  inputAttachments: { type: Array, default: () => [] },
  outputFiles: { type: Array, default: () => [] }
})

const { t } = useI18n()

function fileName(file) {
  return file.filename || file.original_name || 'file'
}
</script>

<style scoped>
.qa-print-view {
  display: none;
}

@media print {
  @page {
    margin: 16mm;
  }

  :global(.qa-screen-view) {
    display: none !important;
  }

  :global(html),
  :global(body) {
    background: #fff !important;
  }

  .qa-print-view {
    display: block;
    color: #1f2937;
    font-family:
      -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
      'Microsoft YaHei', sans-serif;
    font-size: 11pt;
    line-height: 1.6;
    print-color-adjust: exact;
  }

  .qa-print-header {
    border-bottom: 1px solid #d1d5db;
    margin-bottom: 24px;
    padding-bottom: 18px;
  }

  .qa-print-brand {
    color: #2563eb;
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  h1 {
    color: #111827;
    font-size: 22pt;
    line-height: 1.25;
    margin: 10px 0 8px;
  }

  .qa-print-agent,
  .qa-print-date {
    color: #6b7280;
    margin: 2px 0;
  }

  .qa-print-question {
    background: #f3f4f6;
    border: 1px solid #d1d5db;
    border-radius: 8px;
    break-inside: avoid;
    margin-bottom: 24px;
    padding: 16px;
  }

  h2 {
    color: #374151;
    font-size: 9pt;
    letter-spacing: 0.08em;
    margin: 0 0 8px;
    text-transform: uppercase;
  }

  .qa-print-question p {
    margin: 0;
    white-space: pre-wrap;
  }

  .qa-print-files {
    break-inside: avoid;
    margin-top: 18px;
  }

  .qa-print-files h3 {
    color: #4b5563;
    font-size: 10pt;
    margin: 0 0 4px;
  }

  .qa-print-files ul {
    margin: 0;
    padding-left: 20px;
  }

  footer {
    border-top: 1px solid #e5e7eb;
    color: #9ca3af;
    font-size: 8pt;
    margin-top: 32px;
    padding-top: 10px;
  }

  .qa-print-answer :deep(.markdown-table-scroll) {
    overflow: visible !important;
  }

  .qa-print-answer :deep(table) {
    font-size: 8pt;
    table-layout: fixed;
    word-break: break-word;
  }

  .qa-print-answer :deep(pre) {
    break-inside: auto;
    overflow: visible !important;
    white-space: pre-wrap !important;
  }

  .qa-print-answer :deep(img) {
    break-inside: avoid;
    max-height: 220mm;
    object-fit: contain;
  }
}
</style>
