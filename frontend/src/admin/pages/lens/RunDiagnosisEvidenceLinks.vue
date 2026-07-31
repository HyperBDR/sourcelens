<template>
  <div v-if="refs?.length" class="mt-2 flex flex-wrap gap-1.5">
    <button
      v-for="item in refs"
      :key="item"
      type="button"
      class="rounded border border-gray-200 bg-white px-2 py-0.5 font-mono text-[11px] text-primary-700 transition-colors hover:border-primary-300 hover:bg-primary-50"
      @click="$emit('navigate', item)"
    >
      {{ item }}
    </button>
  </div>
</template>

<script setup>
defineProps({
  refs: { type: Array, default: () => [] }
})
defineEmits(['navigate'])
</script>
