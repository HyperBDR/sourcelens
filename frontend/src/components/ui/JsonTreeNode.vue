<template>
  <li class="row" :style="{ paddingLeft: `${depth * indent}px` }">
    <button
      v-if="expandable"
      type="button"
      class="expander"
      :class="{ 'expander-open': open }"
      :aria-label="open ? 'Collapse JSON node' : 'Expand JSON node'"
      @click="open = !open"
    />
    <span
      v-if="keyName !== undefined"
      class="label"
      :class="{ 'label-clickable': expandable }"
      @click="expandable && (open = !open)"
    >
      {{ keyName }}
      <span class="punctuation">:</span>
    </span>
    <template v-if="expandable">
      <span v-if="open" class="punctuation">{{ openBracket }}</span>
      <ul v-if="open" class="children">
        <JsonTreeNode
          v-for="([childKey, childValue], index) in entries"
          :key="array ? String(index) : String(childKey)"
          :key-name="array ? undefined : childKey"
          :value="childValue"
          :depth="depth + 1"
          :indent="indent"
        />
      </ul>
      <span v-if="open" class="punctuation">{{ closeBracket }}</span>
      <span
        v-else
        class="collapsed-content"
        title="Expand JSON node"
        @click="open = true"
        >{{ preview }}</span
      >
    </template>
    <span v-else class="value" :class="valueClass">
      <span class="punctuation" v-if="keyName !== undefined"> </span
      >{{ displayValue }}</span
    >
  </li>
</template>

<script setup>
import { computed, ref } from 'vue'

defineOptions({ name: 'JsonTreeNode' })

const props = defineProps({
  keyName: { type: String, default: undefined },
  value: {
    type: [Object, Array, String, Number, Boolean, null],
    required: true
  },
  depth: { type: Number, default: 0 },
  indent: { type: Number, default: 14 }
})

const open = ref(true)

const expandable = computed(
  () => props.value !== null && typeof props.value === 'object'
)

const array = computed(() => Array.isArray(props.value))

const entries = computed(() => {
  const value = props.value
  if (value === null || typeof value !== 'object') return []
  if (Array.isArray(value)) {
    return value.map((item, index) => [String(index), item])
  }
  return Object.keys(value).map((key) => [key, value[key]])
})

const openBracket = computed(() => (array.value ? '[' : '{'))
const closeBracket = computed(() => (array.value ? ']' : '}'))

const preview = computed(() => {
  const count = entries.value.length
  return `${openBracket.value} ${count} ${count === 1 ? 'item' : 'items'} ${closeBracket.value}`
})

const valueClass = computed(() => {
  const value = props.value
  if (value === null) return 'keyword'
  if (typeof value === 'number') return 'number'
  if (typeof value === 'boolean') return 'keyword'
  if (typeof value === 'string') return 'string'
  return 'other'
})

const displayValue = computed(() => {
  const value = props.value
  if (value === null) return 'null'
  if (typeof value === 'string') return JSON.stringify(value)
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return 'undefined'
})
</script>

<style scoped>
.children {
  margin: 0;
  padding: 0;
  list-style: none;
}

.row {
  position: relative;
  box-sizing: border-box;
  min-width: 100%;
  min-height: 16px;
  margin: 0;
  list-style: none;
  white-space: pre;
}

.row:not(.top-level):hover::after {
  position: absolute;
  z-index: 0;
  top: 0;
  right: 0;
  left: 0;
  height: 16px;
  background: var(--json-tree-hover);
  content: '';
  pointer-events: none;
}

.row > span {
  position: relative;
  z-index: 1;
}

.label {
  margin-right: 3px;
  color: var(--json-tree-property);
  font-weight: 400;
}

.label-clickable {
  cursor: pointer;
}

.punctuation {
  color: var(--json-tree-punctuation);
}

.value {
  color: var(--json-tree-punctuation);
}

.string {
  color: var(--json-tree-string);
}
.number {
  color: var(--json-tree-number);
}
.keyword {
  color: var(--json-tree-keyword);
}
.other {
  color: var(--json-tree-other);
}

.expander {
  position: absolute;
  z-index: 2;
  top: 0;
  left: 0;
  display: inline-flex;
  align-items: center;
  justify-content: flex-start;
  box-sizing: border-box;
  width: 8px;
  height: 16px;
  margin: 0;
  padding: 0;
  border: 0;
  color: var(--json-tree-icon);
  cursor: pointer;
  user-select: none;
  outline: none;
}

.expander::before {
  width: 0;
  height: 0;
  border-top: 4px solid transparent;
  border-bottom: 4px solid transparent;
  border-left: 6px solid currentColor;
  content: '';
  transform: scale(0.75);
  transform-origin: 33.333% center;
  transition: transform 100ms ease-in-out;
}

.expander-open::before {
  transform: rotate(90deg) scale(0.75);
}

.expander:hover {
  color: var(--json-tree-punctuation);
}

.collapsed-content {
  margin: 0 1px;
  color: var(--json-tree-punctuation);
  cursor: pointer;
}
</style>
