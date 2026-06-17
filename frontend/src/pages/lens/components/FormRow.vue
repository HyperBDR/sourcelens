<template>
  <div>
    <label class="mb-1 block text-sm font-medium text-ink-700">
      {{ label }}
    </label>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  label: {
    type: String,
    required: true
  }
})
</script>
