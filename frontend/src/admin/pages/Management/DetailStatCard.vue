<template>
  <div class="min-w-0 px-3 py-4 first:pl-0 last:pr-0">
    <p class="text-xs font-medium uppercase tracking-wide text-ink-400">
      {{ label }}
    </p>
    <p
      class="mt-2 font-semibold text-ink-900"
      :class="compact ? 'text-sm' : 'text-2xl tabular-nums'"
    >
      {{ value ?? 0 }}
    </p>
  </div>
</template>

<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: 0 },
  compact: Boolean
})
</script>
