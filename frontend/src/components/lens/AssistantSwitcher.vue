<template>
  <div
    v-if="mode === 'flyout' && isVisible"
    ref="switcherRef"
    class="assistant-switcher-flyout"
    @mouseenter="open = true"
    @mouseleave="open = false"
  >
    <button
      type="button"
      class="assistant-switcher-flyout-trigger"
      :class="{ 'assistant-switcher-flyout-trigger-open': open }"
      :aria-label="t('settings.modal.allAssistants')"
      @click="toggleOpen"
    >
      <span class="assistant-switcher-flyout-trigger-label">
        {{ t('settings.modal.allAssistants') }}
      </span>
      <svg
        class="assistant-switcher-flyout-trigger-chevron"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        aria-hidden="true"
      >
        <path d="m9 6 6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <Transition
      enter-active-class="transition ease-out duration-100"
      enter-from-class="transform opacity-0 translate-x-1 scale-[0.98]"
      enter-to-class="transform opacity-100 translate-x-0 scale-100"
      leave-active-class="transition ease-in duration-75"
      leave-from-class="transform opacity-100 translate-x-0 scale-100"
      leave-to-class="transform opacity-0 translate-x-1 scale-[0.98]"
    >
      <div v-if="open" class="assistant-switcher-flyout-panel">
        <div class="assistant-switcher-flyout-panel-head">
          <div class="assistant-switcher-flyout-panel-title">
            {{ t('settings.modal.allAssistants') }}
          </div>
          <div v-if="!loading" class="assistant-switcher-flyout-panel-subtitle">
            {{ assistants.length }}
          </div>
        </div>

        <div v-if="loading" class="assistant-switcher-empty">
          {{ t('settings.modal.assistantLoading') }}
        </div>

        <div
          v-else
          class="assistant-switcher-flyout-grid"
          :style="flyoutGridStyle"
        >
          <button
            v-for="assistant in sortedAssistants"
            :key="assistant.uuid"
            type="button"
            class="assistant-switcher-flyout-item"
            :class="
              assistant.slug === currentAssistantSlug
                ? 'assistant-switcher-flyout-item-active'
                : ''
            "
            :title="assistant.name || assistant.slug"
            :aria-label="assistant.name || assistant.slug"
            :disabled="
              Boolean(switchingSlug) && switchingSlug !== assistant.slug
            "
            @click="selectAssistant(assistant.slug)"
          >
            <span
              class="assistant-switcher-flyout-avatar"
              :class="assistantToneClass(assistant)"
            >
              {{ assistantInitial(assistant) }}
            </span>
            <span class="min-w-0 flex-1 truncate text-left text-sm font-medium">
              {{ assistant.name || assistant.slug }}
            </span>
            <svg
              v-if="switchingSlug === assistant.slug"
              class="assistant-switcher-flyout-spinner"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              aria-hidden="true"
            >
              <path
                d="M21 12a9 9 0 1 1-3-6.7"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <svg
              v-else-if="assistant.slug === currentAssistantSlug"
              class="assistant-switcher-flyout-check"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.75"
              aria-hidden="true"
            >
              <path
                d="M20 6 9 17l-5-5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
          </button>
        </div>
      </div>
    </Transition>
  </div>

  <div
    v-if="mode === 'embedded' && isVisible"
    class="assistant-switcher-embedded"
  >
    <div v-if="loading" class="assistant-switcher-empty">
      {{ t('settings.modal.assistantLoading') }}
    </div>
    <div v-else-if="!assistants.length" class="assistant-switcher-empty">
      {{ t('settings.modal.assistantEmpty') }}
    </div>
    <div v-else class="assistant-switcher-embedded-list">
      <button
        v-for="assistant in filteredAssistants"
        :key="assistant.uuid"
        type="button"
        class="assistant-switcher-embedded-item"
        :class="
          assistant.slug === currentAssistantSlug
            ? 'assistant-switcher-embedded-item-active'
            : ''
        "
        :title="assistant.name || assistant.slug"
        :aria-label="assistant.name || assistant.slug"
        :disabled="Boolean(switchingSlug) && switchingSlug !== assistant.slug"
        @click="selectAssistant(assistant.slug)"
      >
        <span class="assistant-switcher-embedded-avatar">
          {{ assistantInitial(assistant) }}
        </span>
        <span class="sr-only">{{ assistant.name || assistant.slug }}</span>
        <svg
          v-if="assistant.slug === currentAssistantSlug"
          class="assistant-switcher-embedded-check"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.75"
          aria-hidden="true"
        >
          <path
            d="M20 6 9 17l-5-5"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
        <svg
          v-else
          class="assistant-switcher-embedded-arrow"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
          aria-hidden="true"
        >
          <path
            d="m10 6 6 6-6 6"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    </div>
  </div>

  <div
    v-if="['floating', 'menu', 'header'].includes(mode) && isVisible"
    class="relative"
    ref="switcherRef"
  >
    <button
      v-if="mode === 'header'"
      type="button"
      class="assistant-switcher-header-trigger"
      :class="open ? 'assistant-switcher-header-trigger-open' : ''"
      :aria-label="t('settings.modal.switchAssistantTitle')"
      @click="toggleOpen"
    >
      <span class="assistant-switcher-header-name">
        {{ currentAssistantLabel }}
      </span>
      <svg
        class="assistant-switcher-header-chevron"
        :class="{ 'rotate-180': open }"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        aria-hidden="true"
      >
        <path d="m6 9 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <button
      v-else
      type="button"
      class="assistant-switcher-trigger"
      :class="[
        mode === 'menu' ? 'assistant-switcher-trigger-menu' : '',
        open ? 'assistant-switcher-trigger-open' : '',
        compact ? 'assistant-switcher-trigger-compact' : ''
      ]"
      :aria-label="t('settings.modal.switchAssistantTitle')"
      @click="toggleOpen"
    >
      <div class="assistant-switcher-mark-wrap">
        <div class="assistant-switcher-mark">
          <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
            <path
              d="M12 2a10 10 0 0 0-8.66 15l-1.2 3.73a1 1 0 0 0 1.27 1.27L7.14 20A10 10 0 1 0 12 2Z"
            />
          </svg>
        </div>
        <span
          v-if="compact && assistants.length > 1"
          class="assistant-switcher-mark-badge"
        >
          {{ assistants.length }}
        </span>
      </div>
      <div
        v-if="!compact"
        class="min-w-0 flex-1 text-left"
        :class="mode === 'menu' ? 'assistant-switcher-menu-copy' : ''"
      >
        <div class="assistant-switcher-label">
          {{ t('settings.modal.switchAssistantTitle') }}
        </div>
        <div class="truncate text-sm font-semibold text-theme">
          {{ currentAssistantLabel }}
        </div>
        <div class="assistant-switcher-hint">
          {{ t('common.current') }}
        </div>
      </div>
      <div v-if="!compact" class="assistant-switcher-count">
        {{ assistants.length }}
      </div>
      <svg
        v-if="!compact"
        class="assistant-switcher-chevron h-4 w-4 shrink-0 text-theme-muted transition-transform"
        :class="{ 'rotate-180': open }"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
        aria-hidden="true"
      >
        <path d="m6 9 6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>

    <Transition
      enter-active-class="transition ease-out duration-100"
      enter-from-class="transform opacity-0 translate-y-1 scale-95"
      enter-to-class="transform opacity-100 translate-y-0 scale-100"
      leave-active-class="transition ease-in duration-75"
      leave-from-class="transform opacity-100 translate-y-0 scale-100"
      leave-to-class="transform opacity-0 translate-y-1 scale-95"
    >
      <div
        v-if="open"
        class="assistant-switcher-panel"
        :class="mode === 'header' ? 'assistant-switcher-panel-down' : ''"
      >
        <div class="assistant-switcher-head">
          <div class="assistant-switcher-title">
            {{ t('settings.modal.switchAssistantTitle') }}
          </div>
          <div class="assistant-switcher-desc">
            {{ t('settings.modal.switchAssistantDesc') }}
          </div>
        </div>

        <div v-if="loading" class="assistant-switcher-empty">
          {{ t('settings.modal.assistantLoading') }}
        </div>
        <div v-else-if="!assistants.length" class="assistant-switcher-empty">
          {{ t('settings.modal.assistantEmpty') }}
        </div>
        <div v-else class="assistant-switcher-list">
          <div v-if="assistants.length > 2" class="assistant-switcher-search">
            <input
              v-model="query"
              type="search"
              name="assistant-search"
              autocomplete="off"
              inputmode="search"
              autocapitalize="none"
              spellcheck="false"
              class="assistant-switcher-input"
              :placeholder="t('common.search')"
            />
          </div>
          <div class="max-h-80 space-y-0.5 overflow-y-auto px-2 pb-2 pt-1">
            <button
              type="button"
              class="assistant-switcher-item assistant-switcher-item-smart"
              :class="isSmartRouting ? 'assistant-switcher-item-active' : ''"
              @click="selectSmartRouting"
            >
              <span
                class="assistant-switcher-item-avatar assistant-tone-violet"
              >
                ✦
              </span>
              <span class="min-w-0 flex-1 text-left">
                <span class="block truncate font-medium">
                  {{ t('lens.chat.smartRouting') }}
                </span>
                <span class="assistant-switcher-item-description">
                  {{ t('lens.chat.smartRoutingDescription') }}
                </span>
              </span>
            </button>
            <button
              v-for="assistant in filteredAssistants"
              :key="assistant.uuid"
              type="button"
              class="assistant-switcher-item"
              :class="
                assistant.slug === currentAssistantSlug
                  ? 'assistant-switcher-item-active'
                  : ''
              "
              @click="selectAssistant(assistant.slug)"
            >
              <span
                class="assistant-switcher-item-avatar"
                :class="assistantToneClass(assistant)"
              >
                {{ assistantInitial(assistant) }}
              </span>
              <span class="min-w-0 flex-1">
                <span class="block truncate font-medium">
                  {{ assistant.name || assistant.slug }}
                </span>
                <span
                  v-if="assistant.description?.trim()"
                  class="assistant-switcher-item-description"
                  :title="assistant.description"
                >
                  {{ assistant.description }}
                </span>
              </span>
              <span
                v-if="assistant.slug === currentAssistantSlug"
                class="assistant-switcher-pill"
              >
                {{ t('common.current') }}
              </span>
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { useLensStore } from '@/store/lens'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const lensStore = useLensStore()

defineProps({
  mode: {
    type: String,
    default: 'floating',
    validator: (value) =>
      ['floating', 'menu', 'embedded', 'flyout', 'header'].includes(value)
  },
  compact: {
    type: Boolean,
    default: false
  }
})

const open = ref(false)
const query = ref('')
const switchingSlug = ref('')
const switchingStartedAt = ref(0)
const switchingTimer = ref(null)
const switcherRef = ref(null)
const flyoutGridStyle = computed(() => {
  const count = sortedAssistants.value.length
  if (count <= 4) {
    return { gridTemplateColumns: 'repeat(1, minmax(0, 1fr))' }
  }
  if (count <= 12) {
    return { gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }
  }
  return { gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }
})

const assistants = computed(() => lensStore.activeAssistants)
const loading = computed(() => lensStore.loading)
const currentAssistantSlug = computed(() => route.params.slug || '')
const isSmartRouting = computed(() => route.name === 'LensSmartChat')

const currentAssistantLabel = computed(() => {
  if (isSmartRouting.value) return t('lens.chat.smartRouting')
  const match = assistants.value.find(
    (item) => item.slug === currentAssistantSlug.value
  )
  return match?.name || match?.slug || t('settings.modal.assistantFallback')
})

function assistantInitial(assistant) {
  const label = (assistant?.name || assistant?.slug || '').trim()
  return label.charAt(0).toUpperCase() || 'P'
}

function assistantToneClass(assistant) {
  const tones = [
    'assistant-tone-sky',
    'assistant-tone-emerald',
    'assistant-tone-violet',
    'assistant-tone-amber',
    'assistant-tone-rose',
    'assistant-tone-cyan',
    'assistant-tone-indigo',
    'assistant-tone-fuchsia'
  ]
  const key = (assistant?.slug || assistant?.name || '').trim()
  const hash = [...key].reduce(
    (acc, char) => (acc * 33 + char.charCodeAt(0)) % tones.length,
    0
  )
  return tones[hash]
}

const assistantCollator = new Intl.Collator(
  ['zh-Hans-u-co-pinyin', 'zh-Hans', 'en'],
  {
    sensitivity: 'base',
    numeric: true
  }
)

const sortedAssistants = computed(() =>
  [...assistants.value].sort((left, right) => {
    const leftName = left.name || left.slug || ''
    const rightName = right.name || right.slug || ''
    return assistantCollator.compare(leftName, rightName)
  })
)

const filteredAssistants = computed(() => {
  const term = query.value.trim().toLowerCase()
  if (!term) return assistants.value
  return assistants.value.filter((assistant) =>
    [assistant.name, assistant.slug]
      .filter(Boolean)
      .some((value) => String(value).toLowerCase().includes(term))
  )
})

const isVisible = computed(() => assistants.value.length > 0)

const toggleOpen = () => {
  open.value = !open.value
}

function clearSwitchingState(delay = 0) {
  if (switchingTimer.value) {
    window.clearTimeout(switchingTimer.value)
    switchingTimer.value = null
  }
  const elapsed = Date.now() - switchingStartedAt.value
  const remain = Math.max(delay, 220 - elapsed)
  switchingTimer.value = window.setTimeout(() => {
    switchingSlug.value = ''
    switchingStartedAt.value = 0
    open.value = false
    switchingTimer.value = null
  }, remain)
}

const selectAssistant = async (slug) => {
  if (!slug || slug === currentAssistantSlug.value) return
  switchingSlug.value = slug
  switchingStartedAt.value = Date.now()
  try {
    await router.push(`/lens/assistants/${slug}/chat`)
  } catch {
    clearSwitchingState(0)
  }
}

const selectSmartRouting = async () => {
  if (isSmartRouting.value) return
  await router.push('/lens/chat')
  open.value = false
}

const handleClickOutside = (event) => {
  if (
    switchingSlug.value ||
    (switcherRef.value && !switcherRef.value.contains(event.target))
  ) {
    open.value = false
  }
}

watch(
  () => route.params.slug,
  (nextSlug) => {
    if (switchingSlug.value && nextSlug === switchingSlug.value) {
      clearSwitchingState()
    }
  }
)

const ensureAssistants = async () => {
  if (assistants.value.length > 0) return
  await lensStore.loadAssistants().catch(() => {})
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  void ensureAssistants()
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
  if (switchingTimer.value) {
    window.clearTimeout(switchingTimer.value)
  }
})
</script>

<style scoped>
.assistant-switcher-trigger {
  @apply flex w-full items-center gap-3 rounded-2xl border border-line bg-surface px-3 py-3 text-left shadow-sm transition-colors;
}

.assistant-switcher-trigger-menu {
  @apply rounded-xl border-0 bg-transparent px-3 py-2 shadow-none;
  box-shadow: none;
}

.assistant-switcher-trigger-menu:hover,
.assistant-switcher-trigger-menu.assistant-switcher-trigger-open {
  @apply bg-line-soft;
  box-shadow: none;
}

.assistant-switcher-trigger:hover,
.assistant-switcher-trigger-open {
  @apply border-primary-200 bg-primary-50;
  box-shadow: 0 10px 24px rgba(73, 93, 125, 0.08);
}

.assistant-switcher-trigger-compact {
  @apply justify-center gap-0 px-0 py-0 min-h-[56px];
}

.assistant-switcher-menu-copy {
  @apply flex-col items-start gap-0;
}

.assistant-switcher-mark-wrap {
  @apply relative flex shrink-0 items-center justify-center;
}

.assistant-switcher-mark {
  @apply flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-ink-900 text-white;
}

.assistant-switcher-mark svg {
  @apply h-[18px] w-[18px];
}

.assistant-switcher-label {
  @apply text-[11px] font-semibold uppercase tracking-wide text-theme-muted;
}

.assistant-switcher-hint {
  @apply mt-0.5 text-[11px] text-theme-muted;
}

.assistant-switcher-count {
  @apply flex h-6 min-w-6 items-center justify-center rounded-full bg-primary-100 px-2 text-[11px] font-semibold text-primary-700;
}

.assistant-switcher-mark-badge {
  @apply absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-primary-500 px-1 text-[10px] font-semibold text-white;
}

.assistant-switcher-chevron {
  @apply ml-auto;
}

.assistant-switcher-header-trigger {
  @apply flex max-w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left transition-colors;
}

.assistant-switcher-header-trigger:hover,
.assistant-switcher-header-trigger-open {
  @apply bg-line-soft;
}

.assistant-switcher-header-name {
  @apply min-w-0 truncate text-base font-semibold text-theme;
}

.assistant-switcher-header-chevron {
  @apply h-4 w-4 shrink-0 text-theme-subtle transition-transform;
}

.assistant-switcher-panel {
  @apply absolute bottom-full left-0 z-50 mb-2 w-[24rem] overflow-hidden rounded-2xl border border-line bg-surface shadow-xl;
}

.assistant-switcher-panel-down {
  @apply bottom-auto top-full mb-0 mt-2;
}

.assistant-switcher-head {
  @apply border-b border-line px-3 py-3;
}

.assistant-switcher-title {
  @apply text-sm font-semibold text-theme;
}

.assistant-switcher-desc {
  @apply mt-1 text-xs text-theme-muted;
}

.assistant-switcher-search {
  @apply px-2 pb-2 pt-2;
}

.assistant-switcher-input {
  @apply w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-theme-secondary outline-none transition-colors;
}

.assistant-switcher-input:focus {
  @apply border-primary-200;
}

.assistant-switcher-list {
  @apply pb-2;
}

.assistant-switcher-empty {
  @apply px-3 py-4 text-sm text-theme-muted;
}

.assistant-switcher-item {
  @apply flex w-full items-start gap-3 rounded-xl px-2.5 py-2 text-left text-sm text-theme-secondary transition-colors;
}

.assistant-switcher-item:hover {
  @apply bg-line-soft text-theme;
}

.assistant-switcher-item-active {
  @apply bg-primary-50 text-primary-700;
}

.assistant-switcher-item-avatar {
  @apply mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white;
}

.assistant-switcher-item-description {
  @apply mt-0.5 overflow-hidden text-xs leading-5 text-theme-muted;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.assistant-switcher-pill {
  @apply mt-0.5 shrink-0 rounded-full bg-primary-100 px-2 py-0.5 text-xs font-medium text-primary-700;
}

@media (max-width: 1023px) {
  .assistant-switcher-header-trigger {
    min-height: 44px;
  }

  .assistant-switcher-header-name {
    @apply text-sm;
  }

  .assistant-switcher-panel-down {
    position: fixed;
    top: calc(env(safe-area-inset-top) + 3.5rem);
    right: 1rem;
    left: 1rem;
    width: auto;
    max-height: calc(100dvh - env(safe-area-inset-top) - 4.5rem);
    overflow-y: auto;
  }
}

.assistant-switcher-embedded {
  @apply w-full;
}

.assistant-switcher-embedded-list {
  @apply space-y-1 px-2 py-1;
}

.assistant-switcher-embedded-item {
  @apply flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-theme-secondary transition-colors;
}

.assistant-switcher-embedded-item:hover {
  @apply bg-line-soft text-theme;
}

.assistant-switcher-embedded-item-active {
  @apply bg-primary-50 text-primary-700;
}

.assistant-switcher-embedded-avatar {
  @apply flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-ink-900 text-[10px] font-semibold text-white;
}

.assistant-switcher-embedded-check {
  @apply h-4 w-4 shrink-0 text-primary-600;
}

.assistant-switcher-embedded-arrow {
  @apply h-4 w-4 shrink-0 text-theme-subtle;
}

.assistant-switcher-flyout {
  @apply relative w-full;
}

.assistant-switcher-flyout-trigger {
  @apply flex w-full items-center justify-between gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium text-theme-secondary transition-colors;
}

.assistant-switcher-flyout-trigger:hover,
.assistant-switcher-flyout-trigger-open {
  @apply bg-line-soft text-theme;
}

.assistant-switcher-flyout-trigger-label {
  @apply truncate;
}

.assistant-switcher-flyout-trigger-chevron {
  @apply h-4 w-4 shrink-0 text-theme-subtle;
}

.assistant-switcher-flyout-panel {
  @apply absolute left-full top-0 z-50 ml-2 overflow-hidden rounded-2xl border border-line bg-surface shadow-xl;
  min-width: 24rem;
  max-width: min(44rem, calc(100vw - 24rem));
}

.assistant-switcher-flyout-panel-head {
  @apply flex items-center justify-between border-b border-line px-4 py-3;
}

.assistant-switcher-flyout-panel-title {
  @apply text-sm font-semibold text-theme;
}

.assistant-switcher-flyout-panel-subtitle {
  @apply text-xs text-theme-muted;
}

.assistant-switcher-flyout-grid {
  @apply max-h-[24rem] gap-2 overflow-y-auto p-3;
  display: grid;
}

.assistant-switcher-flyout-item {
  @apply flex items-center gap-2 rounded-xl border border-transparent px-3 py-2 text-left text-theme-secondary transition-colors;
}

.assistant-switcher-flyout-item:hover {
  @apply bg-line-soft text-theme;
}

.assistant-switcher-flyout-item-active {
  @apply border-primary-100 bg-primary-50 text-primary-700;
}

.assistant-switcher-flyout-item:disabled {
  @apply cursor-wait opacity-70;
}

.assistant-switcher-flyout-avatar {
  @apply flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold text-white;
}

.assistant-tone-sky {
  background: linear-gradient(135deg, #2563eb, #0ea5e9);
}

.assistant-tone-emerald {
  background: linear-gradient(135deg, #059669, #22c55e);
}

.assistant-tone-violet {
  background: linear-gradient(135deg, #7c3aed, #a855f7);
}

.assistant-tone-amber {
  background: linear-gradient(135deg, #d97706, #f59e0b);
}

.assistant-tone-rose {
  background: linear-gradient(135deg, #e11d48, #fb7185);
}

.assistant-tone-cyan {
  background: linear-gradient(135deg, #0891b2, #22d3ee);
}

.assistant-tone-indigo {
  background: linear-gradient(135deg, #4f46e5, #6366f1);
}

.assistant-tone-fuchsia {
  background: linear-gradient(135deg, #c026d3, #d946ef);
}

.assistant-switcher-flyout-check {
  @apply h-4 w-4 shrink-0 text-primary-600;
}

.assistant-switcher-flyout-spinner {
  @apply h-4 w-4 shrink-0 text-primary-600;
  animation: assistant-spin 0.8s linear infinite;
}

@keyframes assistant-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
