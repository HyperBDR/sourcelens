<template>
  <div class="routing-scope-picker" :class="{ 'is-mobile': mobile }">
    <button
      type="button"
      class="routing-scope-trigger"
      :aria-expanded="open"
      aria-controls="participating-assistants-panel"
      @click="$emit('open')"
    >
      {{ t('lens.chat.participatingAssistants', { count }) }}
    </button>
    <div
      v-if="open"
      class="routing-scope-layer"
      :class="{ 'is-mobile': mobile }"
      @click.self="handleBackdropClick"
      @keydown.esc.stop="$emit('cancel')"
    >
      <div
        id="participating-assistants-panel"
        class="routing-scope-panel"
        :role="mobile ? 'dialog' : undefined"
        :aria-modal="mobile ? 'true' : undefined"
      >
        <p class="text-xs leading-5 text-ink-500">
          {{ t('lens.chat.participatingAssistantsHint') }}
        </p>
        <p
          class="mt-2 rounded-md border border-warning-200 bg-warning-50 px-2.5 py-2 text-xs leading-5 text-warning-700"
        >
          {{ t('lens.chat.participatingAssistantsAccuracyWarning') }}
        </p>
        <div class="mt-3 flex items-center gap-2">
          <input
            ref="searchInput"
            :value="query"
            type="search"
            name="participating-assistant-search"
            autocomplete="off"
            inputmode="search"
            :aria-label="t('lens.chat.searchParticipatingAssistants')"
            :placeholder="t('lens.chat.searchParticipatingAssistants')"
            class="min-w-0 flex-1 rounded-md border border-line bg-surface px-2.5 py-1.5 text-sm text-ink-900 outline-none placeholder:text-ink-400 focus:border-brand-400 focus:ring-1 focus:ring-brand-400"
            @input="$emit('update:query', $event.target.value)"
          />
          <button
            type="button"
            :disabled="!candidateCount"
            :aria-pressed="allSelected"
            class="shrink-0 rounded px-2 py-1.5 text-xs font-medium text-brand-700 hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-50"
            @click="$emit('toggle-all')"
          >
            {{
              allSelected
                ? t('lens.chat.clearAllParticipatingAssistants')
                : t('common.selectAll')
            }}
          </button>
        </div>
        <div class="routing-scope-list">
          <label
            v-for="assistant in filteredCandidates"
            :key="assistant.uuid"
            class="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-surface-sunken"
          >
            <input
              type="checkbox"
              :value="assistant.uuid"
              :checked="draft.includes(assistant.uuid)"
              class="h-4 w-4 rounded border-line text-brand-600 focus:ring-brand-500"
              @change="toggleAssistant(assistant.uuid, $event.target.checked)"
            />
            <span class="min-w-0 flex-1 truncate">
              {{ assistant.name }}
            </span>
            <span class="text-xs text-ink-500">
              {{ assistantCapabilityLabel(assistant.capability) }}
            </span>
          </label>
          <p
            v-if="!filteredCandidates.length"
            class="px-2 py-4 text-center text-xs text-ink-500"
          >
            {{ t('lens.chat.participatingAssistantsEmpty') }}
          </p>
        </div>
        <div class="mt-3 flex justify-end gap-2">
          <button
            type="button"
            class="routing-scope-action text-ink-600 hover:bg-surface-sunken"
            @click="$emit('cancel')"
          >
            {{ t('common.cancel') }}
          </button>
          <button
            type="button"
            class="routing-scope-action bg-brand-600 font-medium text-white hover:bg-brand-700"
            @click="$emit('save')"
          >
            {{ t('common.save') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  allSelected: { type: Boolean, default: false },
  candidateCount: { type: Number, default: 0 },
  count: { type: Number, default: 0 },
  draft: { type: Array, default: () => [] },
  filteredCandidates: { type: Array, default: () => [] },
  mobile: { type: Boolean, default: false },
  open: { type: Boolean, default: false },
  query: { type: String, default: '' }
})

const emit = defineEmits([
  'cancel',
  'open',
  'save',
  'toggle-all',
  'update:draft',
  'update:query'
])

const { t } = useI18n()
const searchInput = ref(null)

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    await nextTick()
    searchInput.value?.focus()
  }
)

function assistantCapabilityLabel(capability) {
  const labels = {
    code_analysis: 'codeAnalysis',
    general_chat: 'generalChat',
    knowledge_qa: 'knowledgeQa'
  }
  return t(`lens.chat.assistantTypes.${labels[capability] || 'generalChat'}`)
}

function handleBackdropClick() {
  if (props.mobile) emit('cancel')
}

function toggleAssistant(uuid, checked) {
  const selected = new Set(props.draft)
  if (checked) selected.add(uuid)
  else selected.delete(uuid)
  emit('update:draft', [...selected])
}
</script>

<style scoped>
.routing-scope-picker {
  @apply relative mb-2;
}

.routing-scope-trigger {
  @apply rounded-md border border-line bg-surface px-2.5 py-1 text-xs
    font-medium text-ink-600 transition-colors;
}

.routing-scope-trigger:hover {
  @apply border-primary-300 text-primary-700;
}

.routing-scope-layer {
  @apply absolute bottom-full left-0 z-20 mb-2;
}

.routing-scope-panel {
  @apply w-80 rounded-lg border border-line bg-surface p-3 shadow-lg;
}

.routing-scope-list {
  @apply mt-2 max-h-56 space-y-1 overflow-y-auto;
}

.routing-scope-action {
  @apply min-h-8 rounded px-2 py-1 text-xs;
}

.routing-scope-picker.is-mobile {
  @apply mb-2 flex-shrink-0;
}

.routing-scope-picker.is-mobile .routing-scope-trigger {
  @apply min-h-11 w-full text-sm;
}

.routing-scope-layer.is-mobile {
  @apply fixed inset-0 z-50 m-0 flex items-end bg-black/30 p-3;
}

.routing-scope-layer.is-mobile .routing-scope-panel {
  @apply flex max-h-[80dvh] w-full flex-col rounded-xl p-4;
}

.routing-scope-layer.is-mobile .routing-scope-list {
  @apply max-h-none min-h-0 flex-1;
}

.routing-scope-layer.is-mobile .routing-scope-action {
  @apply min-h-11 px-4 text-sm;
}
</style>
