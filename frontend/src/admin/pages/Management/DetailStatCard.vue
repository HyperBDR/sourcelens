<template>
  <div class="stat-card min-w-0 px-4 py-4">
    <p
      class="stat-label text-xs font-medium uppercase tracking-wide text-ink-400"
    >
      {{ label }}
    </p>
    <p
      class="stat-value mt-2 font-semibold text-ink-900 tabular-nums"
      :class="compact ? 'text-sm leading-5' : 'text-2xl leading-none'"
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

<style scoped>
.stat-card {
  @apply flex flex-col;
}

.stat-label {
  min-height: 2.5rem;
  line-height: 1.25rem;
}

.stat-value {
  min-height: 2rem;
}
</style>
