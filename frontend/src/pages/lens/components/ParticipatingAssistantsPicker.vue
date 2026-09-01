<template>
  <div class="routing-scope-picker" :class="{ 'is-mobile': mobile }">
    <button
      type="button"
      class="routing-scope-entry"
      :aria-expanded="open"
      :aria-label="
        t('lens.chat.participatingAssistants', {
          count: selectedAssistants.length
        })
      "
      aria-controls="participating-assistants-panel"
      @click="handleEntryClick"
    >
      <span class="routing-scope-avatar-stack" aria-hidden="true">
        <span
          v-for="assistant in selectedAssistants.slice(0, 4)"
          :key="assistant.uuid"
          class="routing-scope-avatar routing-scope-entry-avatar"
          :style="{ backgroundColor: assistantColor(assistant) }"
        >
          {{ assistantInitials(assistant.name) }}
        </span>
      </span>
      <span class="routing-scope-entry-label">
        {{
          t('lens.chat.participatingAssistants', {
            count: selectedAssistants.length
          })
        }}
      </span>
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
        role="dialog"
        aria-modal="true"
        :aria-labelledby="'participating-assistants-title'"
      >
        <div class="routing-scope-heading">
          <div>
            <h2 id="participating-assistants-title" class="routing-scope-title">
              {{ t('lens.chat.participatingAssistantsTitle') }}
            </h2>
            <p class="routing-scope-hint">
              {{ t('lens.chat.participatingAssistantsHint') }}
            </p>
          </div>
        </div>
        <div class="routing-scope-toolbar">
          <label class="routing-scope-search">
            <span class="sr-only">
              {{ t('lens.chat.searchParticipatingAssistants') }}
            </span>
            <input
              ref="searchInput"
              :value="query"
              type="search"
              name="participating-assistant-search"
              autocomplete="off"
              inputmode="search"
              :aria-label="t('lens.chat.searchParticipatingAssistants')"
              :placeholder="t('lens.chat.searchParticipatingAssistants')"
              @input="$emit('update:query', $event.target.value)"
            />
          </label>
          <button
            type="button"
            :disabled="readonly || !candidateCount"
            :aria-pressed="allSelected"
            class="routing-scope-select-all"
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
          <div v-for="group in candidateGroups" :key="group.capability">
            <p class="routing-scope-group-title">
              {{ assistantCapabilityLabel(group.capability) }}
            </p>
            <label
              v-for="assistant in group.assistants"
              :key="assistant.uuid"
              class="routing-scope-option"
              :class="{ 'is-selected': draft.includes(assistant.uuid) }"
            >
              <input
                type="checkbox"
                :value="assistant.uuid"
                :checked="draft.includes(assistant.uuid)"
                class="routing-scope-checkbox sr-only"
                :disabled="readonly"
                @change="toggleAssistant(assistant.uuid, $event.target.checked)"
              />
              <span
                class="routing-scope-check"
                :class="{ 'is-checked': draft.includes(assistant.uuid) }"
                aria-hidden="true"
              >
                <svg
                  v-if="draft.includes(assistant.uuid)"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <path
                    d="m3 8 3 3 7-7"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </span>
              <span
                class="routing-scope-avatar routing-scope-option-avatar"
                :style="{ backgroundColor: assistantColor(assistant) }"
                aria-hidden="true"
              >
                {{ assistantInitials(assistant.name) }}
              </span>
              <span class="routing-scope-option-name">
                {{ assistant.name }}
              </span>
            </label>
          </div>
          <p v-if="!filteredCandidates.length" class="routing-scope-empty">
            {{ t('lens.chat.participatingAssistantsEmpty') }}
          </p>
        </div>
        <div class="routing-scope-footer">
          <p
            class="routing-scope-count"
            :class="{
              'is-warning': draftCount > recommendedMax,
              'is-error': draftCount === 0
            }"
          >
            {{ selectionStatusText }}
          </p>
          <div class="routing-scope-actions">
            <button
              type="button"
              class="routing-scope-action text-ink-600 hover:bg-surface-sunken"
              @click="$emit('cancel')"
            >
              {{ readonly ? t('common.close') : t('common.cancel') }}
            </button>
            <button
              v-if="!readonly"
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
  </div>
</template>

<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps({
  allSelected: { type: Boolean, default: false },
  candidates: { type: Array, default: () => [] },
  candidateCount: { type: Number, default: 0 },
  draft: { type: Array, default: () => [] },
  filteredCandidates: { type: Array, default: () => [] },
  mobile: { type: Boolean, default: false },
  open: { type: Boolean, default: false },
  query: { type: String, default: '' },
  selectedUuids: { type: Array, default: () => [] },
  readonly: { type: Boolean, default: false }
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
const recommendedMax = 4
const assistantColors = [
  '#2563eb',
  '#7c3aed',
  '#0d9488',
  '#d97706',
  '#475569',
  '#e11d48'
]
const selectedAssistants = computed(() =>
  props.candidates.filter((assistant) =>
    props.selectedUuids.includes(assistant.uuid)
  )
)

const draftCount = computed(() => props.draft.length)
const candidateGroups = computed(() => {
  const order = ['knowledge_qa', 'code_analysis', 'general_chat']
  return order
    .map((capability) => ({
      capability,
      assistants: props.filteredCandidates.filter(
        (assistant) => assistant.capability === capability
      )
    }))
    .filter((group) => group.assistants.length)
})
const selectionStatusText = computed(() => {
  if (draftCount.value === 0) {
    return t('lens.chat.participatingAssistantsNone')
  }
  return t('lens.chat.participatingAssistantsCount', {
    count: draftCount.value,
    max: recommendedMax
  })
})

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

function assistantInitials(name) {
  const words = String(name || '')
    .trim()
    .split(/\s+/)
    .filter(Boolean)
  if (!words.length) return '?'
  return words
    .slice(0, 2)
    .map((word) => word[0])
    .join('')
    .toUpperCase()
}

function assistantColor(assistant) {
  const source = String(assistant.uuid || assistant.name || '')
  const index = [...source].reduce(
    (total, character) => total + character.codePointAt(0),
    0
  )
  return assistantColors[index % assistantColors.length]
}

function handleBackdropClick() {
  emit('cancel')
}

function handleEntryClick() {
  emit('open')
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
  @apply relative mb-3;
}

.routing-scope-entry:focus-visible,
.routing-scope-select-all:focus-visible,
.routing-scope-action:focus-visible {
  @apply outline-none ring-2 ring-primary-300 ring-offset-1;
}

.routing-scope-avatar {
  @apply flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full
    border-2 border-white text-[9.5px] font-bold leading-none text-white;
}

.routing-scope-entry {
  @apply inline-flex max-w-full items-center gap-2 rounded-[20px] border-0
    py-1.5 pl-1.5 pr-2 text-[12.5px] font-medium transition-colors;
  background: #f4f4f5;
  color: #3f3f46;
}

.routing-scope-entry:hover {
  background: #e4e4e7;
}

.routing-scope-avatar-stack {
  @apply flex items-center;
}

.routing-scope-entry-avatar {
  @apply -ml-1.5;
}

.routing-scope-entry-label {
  @apply truncate pr-1.5;
}

.routing-scope-layer {
  @apply fixed inset-0 z-50 flex items-center justify-center p-4;
  background: rgba(24, 24, 27, 0.32);
}

.routing-scope-panel {
  @apply flex max-h-[min(640px,calc(100dvh-2rem))] w-[min(520px,calc(100vw-2rem))]
    flex-col overflow-hidden rounded-[16px] bg-surface;
  box-shadow: 0 24px 60px rgb(0 0 0 / 22%);
}

.routing-scope-heading {
  @apply px-[22px] pt-5;
}

.routing-scope-title {
  @apply text-[15px] font-semibold text-ink-900;
}

.routing-scope-hint {
  @apply mt-0.5 text-[12.5px] leading-5 text-ink-400;
}

.routing-scope-toolbar {
  @apply flex items-center gap-2.5 px-[22px] pb-2 pt-3;
}

.routing-scope-search {
  @apply flex min-w-0 flex-1 items-center rounded-[8px] border border-line
    bg-surface px-3 py-2 text-ink-400 transition-colors focus-within:border-primary-400;
}

.routing-scope-search input {
  @apply min-w-0 flex-1 border-0 bg-transparent p-0 text-[13px] text-ink-900 outline-none
    placeholder:text-ink-400;
}

.routing-scope-search input::-webkit-search-cancel-button {
  @apply cursor-pointer;
}

.routing-scope-select-all {
  @apply shrink-0 rounded-md px-0 py-2 text-[12.5px] font-semibold text-primary-700
    transition-colors hover:bg-primary-50 disabled:cursor-not-allowed disabled:opacity-50;
}

.routing-scope-list {
  @apply min-h-0 flex-1 overflow-y-auto px-[22px] pb-2 pt-1;
}

.routing-scope-group-title {
  @apply mb-1 mt-2.5 px-2 text-[11px] font-bold uppercase tracking-[0.03em]
    text-ink-400;
}

.routing-scope-option {
  @apply mb-0.5 flex cursor-pointer items-center gap-2.5 rounded-[8px] px-2
    py-[9px] text-[13px] transition-colors hover:bg-surface-sunken;
}

.routing-scope-option.is-selected {
  background: #f6f7fb;
}

.routing-scope-check {
  @apply flex h-4 w-4 shrink-0 items-center justify-center rounded-[5px] border
    border-line-strong bg-surface text-white transition-colors;
}

.routing-scope-check.is-checked {
  @apply border-primary-600 bg-primary-600;
}

.routing-scope-check svg {
  @apply h-3 w-3;
}

.routing-scope-option-avatar {
  @apply h-[26px] w-[26px] border-0 text-[10.5px];
}

.routing-scope-option-name {
  @apply min-w-0 flex-1 truncate font-medium text-ink-800;
}

.routing-scope-empty {
  @apply px-2 py-8 text-center text-xs text-ink-500;
}

.routing-scope-footer {
  @apply border-t border-line-soft px-[22px] py-3;
}

.routing-scope-count {
  @apply mb-2.5 min-w-0 text-xs text-ink-500;
}

.routing-scope-count.is-warning {
  color: #9a6700;
}

.routing-scope-count.is-error {
  color: #c2410c;
}

.routing-scope-actions {
  @apply flex shrink-0 items-center justify-end gap-2;
}

.routing-scope-action {
  @apply min-h-8 rounded-[8px] px-3.5 py-1.5 text-[13px];
}

.routing-scope-picker.is-mobile {
  @apply mb-3 flex-shrink-0;
}

.routing-scope-layer.is-mobile {
  @apply items-end p-3;
}

.routing-scope-layer.is-mobile .routing-scope-panel {
  @apply max-h-[80dvh] w-full rounded-[16px];
}

.routing-scope-layer.is-mobile .routing-scope-heading,
.routing-scope-layer.is-mobile .routing-scope-toolbar,
.routing-scope-layer.is-mobile .routing-scope-footer {
  @apply px-4;
}

.routing-scope-layer.is-mobile .routing-scope-select-all {
  @apply min-h-11;
}

.routing-scope-layer.is-mobile .routing-scope-list {
  @apply px-4;
}

.routing-scope-layer.is-mobile .routing-scope-action {
  @apply min-h-11 px-4 text-sm;
}

@media (max-width: 420px) {
  .routing-scope-count {
    @apply leading-4;
  }
}
</style>
