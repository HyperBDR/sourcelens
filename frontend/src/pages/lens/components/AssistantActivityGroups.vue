<template>
  <div class="runtime-assistant-groups">
    <details
      v-for="group in groups"
      :key="group.key"
      :open="live"
      class="runtime-assistant-card"
    >
      <summary class="runtime-assistant-summary">
        <span
          class="runtime-assistant-status-indicator"
          :class="{ 'is-live': live }"
          aria-hidden="true"
        >
          {{ live ? '' : '✓' }}
        </span>
        <span class="runtime-assistant-summary-content">
          <span class="runtime-assistant-heading">
            <strong>{{ group.assistantName }}</strong>
            <span class="runtime-assistant-status-text">
              {{
                live
                  ? t('lens.chat.runtime.running')
                  : t('lens.chat.runtime.completed')
              }}
            </span>
          </span>
          <span v-if="group.tasks[0]" class="runtime-assistant-task-summary">
            {{ group.tasks[0] }}
          </span>
        </span>
        <span class="runtime-assistant-chevron" aria-hidden="true">⌄</span>
      </summary>

      <div class="runtime-assistant-details">
        <div
          v-if="group.summaryItems.length"
          class="runtime-assistant-activity-list"
        >
          <div
            v-for="activity in group.summaryItems"
            :key="activity.kind"
            class="runtime-assistant-activity"
          >
            <span aria-hidden="true">✓</span>
            <span>{{ activityLabel(activity.kind) }}</span>
            <span
              v-if="activity.count > 1"
              class="runtime-assistant-activity-count"
            >
              ×{{ activity.count }}
            </span>
          </div>
        </div>

        <details v-if="group.tasks.length" class="runtime-assistant-full-task">
          <summary>{{ t('lens.chat.runtime.fullTask') }}</summary>
          <p v-for="task in group.tasks" :key="task">{{ task }}</p>
        </details>
      </div>
    </details>
  </div>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

defineProps({
  groups: {
    type: Array,
    default: () => []
  },
  live: {
    type: Boolean,
    default: false
  }
})

const { t } = useI18n()

function activityLabel(kind) {
  const known = new Set([
    'analyzingResults',
    'findingCapability',
    'preparingOutput',
    'queryingData',
    'readingContext',
    'readingSources',
    'searchingSources',
    'usingCapability'
  ])
  const safeKind = known.has(kind) ? kind : 'usingCapability'
  return t(`lens.chat.runtime.activity.${safeKind}`)
}
</script>

<style scoped>
.runtime-assistant-groups {
  display: grid;
  gap: 0.45rem;
  margin-bottom: 0.5rem;
}

.runtime-assistant-card {
  border: 1px solid var(--sl-border-default);
  border-radius: 0.45rem;
  background: var(--sl-bg-raised);
}

.runtime-assistant-summary {
  display: flex;
  min-height: 2.75rem;
  align-items: flex-start;
  gap: 0.5rem;
  padding: 0.45rem;
  cursor: pointer;
  list-style: none;
}

.runtime-assistant-summary::-webkit-details-marker {
  display: none;
}

.runtime-assistant-summary-content {
  min-width: 0;
  flex: 1;
}

.runtime-assistant-heading {
  display: flex;
  align-items: baseline;
  gap: 0.45rem;
  color: var(--sl-text-primary);
  font-size: 0.72rem;
}

.runtime-assistant-status-text {
  color: var(--sl-text-muted);
  font-size: 0.68rem;
  font-weight: 400;
}

.runtime-assistant-status-indicator {
  display: inline-flex;
  width: 0.9rem;
  height: 0.9rem;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  margin-top: 0.1rem;
  color: var(--sl-success);
  font-size: 0.68rem;
}

.runtime-assistant-status-indicator.is-live {
  border: 2px solid var(--sl-border-default);
  border-top-color: var(--sl-accent);
  border-radius: 999px;
  animation: runtime-assistant-spin 0.8s linear infinite;
}

.runtime-assistant-task-summary {
  display: -webkit-box;
  margin-top: 0.15rem;
  overflow: hidden;
  color: var(--sl-text-secondary);
  font-size: 0.7rem;
  line-height: 1rem;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.runtime-assistant-chevron {
  flex: 0 0 auto;
  color: var(--sl-text-muted);
  transition: transform 0.16s ease;
}

.runtime-assistant-card[open]
  > .runtime-assistant-summary
  .runtime-assistant-chevron {
  transform: rotate(180deg);
}

.runtime-assistant-details {
  padding: 0 0.45rem 0.45rem 1.85rem;
}

.runtime-assistant-activity-list {
  display: grid;
  gap: 0.15rem;
}

.runtime-assistant-activity {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  color: var(--sl-text-muted);
  font-size: 0.7rem;
}

.runtime-assistant-activity-count {
  font-variant-numeric: tabular-nums;
}

.runtime-assistant-full-task {
  margin-top: 0.35rem;
  color: var(--sl-text-muted);
  font-size: 0.68rem;
}

.runtime-assistant-full-task > summary {
  width: fit-content;
  min-height: 1.5rem;
  cursor: pointer;
  color: var(--sl-accent);
}

.runtime-assistant-full-task p {
  margin: 0.25rem 0 0;
  padding: 0.35rem;
  border-radius: 0.3rem;
  background: var(--sl-bg-hover);
  color: var(--sl-text-secondary);
  line-height: 1.05rem;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

@keyframes runtime-assistant-spin {
  to {
    transform: rotate(360deg);
  }
}

@media (prefers-reduced-motion: reduce) {
  .runtime-assistant-status-indicator.is-live {
    animation: none;
  }

  .runtime-assistant-chevron {
    transition: none;
  }
}
</style>
