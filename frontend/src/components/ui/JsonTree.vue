<template>
  <div class="json-tree sl-scrollbar">
    <template v-if="data !== null && typeof data === 'object'">
      <ul class="container">
        <JsonTreeNode :value="data" :depth="0" :indent="indent" />
      </ul>
    </template>
    <p v-else class="empty">{{ data == null ? 'null' : String(data) }}</p>
  </div>
</template>

<script setup>
import JsonTreeNode from './JsonTreeNode.vue'

defineProps({
  data: {
    type: [Object, Array, String, Number, Boolean, null],
    required: true
  },
  indent: { type: Number, default: 14 }
})
</script>

<style scoped>
.json-tree {
  --json-tree-property: #881391;
  --json-tree-string: #c41a16;
  --json-tree-number: #1c00cf;
  --json-tree-keyword: #1c00cf;
  --json-tree-punctuation: #202124;
  --json-tree-icon: #5f6368;
  --json-tree-other: #61666b;
  --json-tree-hover: rgb(60 64 67 / 4%);

  min-width: 0;
  min-height: 0;
  flex: 1;
  overflow: auto;
  position: relative;
  color: var(--t-text-1);
  background: var(--t-bg-1);
  font:
    12px/16px ui-monospace,
    SFMono-Regular,
    Menlo,
    monospace;
  overscroll-behavior-x: contain;
}

:root[data-theme='dark'] .json-tree {
  --json-tree-property: #5db0d7;
  --json-tree-string: #f28b82;
  --json-tree-number: #99c8ff;
  --json-tree-keyword: #99c8ff;
  --json-tree-punctuation: #e8eaed;
  --json-tree-icon: #9aa0a6;
  --json-tree-other: #adb2b8;
  --json-tree-hover: rgb(232 234 237 / 5%);
}

.container {
  box-sizing: border-box;
  width: max-content;
  min-width: 100%;
  margin: 0;
  padding: 6px 8px 8px;
  list-style: none;
  white-space: pre;
}

.empty {
  margin: 0;
  padding: 14px;
  color: var(--t-text-3);
  font-size: 12px;
}
</style>
