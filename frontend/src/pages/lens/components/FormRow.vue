<template>
  <div>
    <label
      class="mb-1 block text-sm font-medium text-ink-700"
      :for="forId || undefined"
    >
      {{ label }}
      <span v-if="required" class="text-danger-600">*</span>
    </label>
    <slot />
  </div>
</template>

<script setup>
defineProps({
  label: {
    type: String,
    required: true
  },
  required: {
    type: Boolean,
    default: false
  },
  forId: {
    type: String,
    default: ''
  }
})
</script>
