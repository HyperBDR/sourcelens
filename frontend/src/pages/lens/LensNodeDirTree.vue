<template>
  <ul class="space-y-0.5">
    <li v-for="node in nodes" :key="node.path">
      <button
        type="button"
        class="flex w-full items-center gap-1.5 rounded px-1.5 py-1 text-left text-sm text-ink-700 transition-colors hover:bg-surface-sunken"
        @click="toggle(node)"
      >
        <span
          class="flex h-4 w-4 flex-shrink-0 items-center justify-center text-ink-400"
        >
          <svg
            v-if="node.loading"
            class="h-3.5 w-3.5 animate-spin"
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
          <svg
            v-else
            class="h-3.5 w-3.5 transition-transform"
            :class="node.expanded ? 'rotate-90' : ''"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 5l7 7-7 7"
            />
          </svg>
        </span>
        <svg
          class="h-4 w-4 flex-shrink-0 text-brand-500"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"
          />
        </svg>
        <span class="truncate font-mono text-xs">{{ node.name }}</span>
        <span
          v-if="node.error"
          class="ml-1 flex-shrink-0 text-xs text-danger-600"
        >
          {{ t('lensAdmin.detail.loadDirsFailed') }}
        </span>
      </button>

      <div v-if="node.expanded" class="ml-3 border-l border-line pl-2">
        <LensNodeDirTree
          v-if="node.children && node.children.length"
          :nodes="node.children"
          :loader="loader"
        />
        <p
          v-else-if="node.children && !node.children.length"
          class="px-1.5 py-1 text-xs italic text-ink-400"
        >
          {{ t('lensAdmin.detail.nodeEmpty') }}
        </p>
      </div>
    </li>
  </ul>
</template>

<script setup>
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const props = defineProps({
  // Reactive tree nodes; each node carries its own
  // {path, name, children, expanded, loading} state.
  nodes: {
    type: Array,
    required: true
  },
  // (path) => Promise<childNode[]>; resolves the next level on demand.
  loader: {
    type: Function,
    required: true
  }
})

async function toggle(node) {
  if (node.loading) return
  if (node.expanded) {
    node.expanded = false
    return
  }
  if (node.children === null) {
    node.loading = true
    node.error = false
    try {
      const children = await props.loader(node.path)
      // loader returns null on failure; keep children null so a click retries.
      if (children === null) {
        node.error = true
      } else {
        node.children = children
      }
    } finally {
      node.loading = false
    }
  }
  if (node.children !== null) {
    node.expanded = true
  }
}
</script>
