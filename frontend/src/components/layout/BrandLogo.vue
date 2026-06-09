<template>
  <div :class="containerClass">
    <img
      v-if="showMark"
      :src="markSrc"
      :alt="altText"
      :class="markClass"
    />
    <img
      v-if="showWordmark"
      :src="wordmarkSrc"
      :alt="altText"
      :class="wordmarkClass"
    />
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  altText: {
    type: String,
    default: 'SourceLens'
  },
  variant: {
    type: String,
    default: 'wordmark',
    validator: (value) => ['wordmark', 'mark', 'responsive'].includes(value)
  },
  tone: {
    type: String,
    default: 'light',
    validator: (value) => ['light', 'dark'].includes(value)
  },
  wrapperClass: {
    type: String,
    default: ''
  }
})

const markSrc = computed(() => '/brand/logo_transparent.png')

const wordmarkSrc = computed(
  () => '/brand/logo_with_text_transparent.png'
)

const showMark = computed(() => props.variant !== 'wordmark')
const showWordmark = computed(() => props.variant !== 'mark')

const containerClass = computed(() => {
  const classes = ['flex items-center gap-3', props.wrapperClass]
  return classes.filter(Boolean).join(' ')
})

const markClass = computed(() => {
  const sizeClasses = {
    sm: 'h-10 w-10',
    md: 'h-12 w-12',
    lg: 'h-14 w-14'
  }
  if (props.variant === 'responsive') {
    return `${sizeClasses.md} shrink-0 object-contain sm:hidden`
  }
  return `${sizeClasses.md} shrink-0 object-contain`
})

const wordmarkClass = computed(() => {
  const sizeClasses = {
    sm: 'w-[160px] h-auto',
    md: 'w-[190px] h-auto',
    lg: 'w-[220px] h-auto'
  }
  if (props.variant === 'responsive') {
    return `hidden ${sizeClasses.md} object-contain sm:block`
  }
  return `${sizeClasses.md} object-contain`
})
</script>
