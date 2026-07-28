<template>
  <div
    v-if="selectedCount > 0"
    class="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-primary-200 bg-primary-50 px-3 py-2"
    role="region"
    :aria-label="t('common.bulkActions')"
  >
    <div class="flex items-center gap-3">
      <span class="text-sm font-medium text-primary-800">
        {{ t('common.selectedCount', { count: selectedCount }) }}
      </span>
      <button
        type="button"
        class="text-sm text-primary-700 underline-offset-2 hover:underline"
        @click="clearSelection"
      >
        {{ t('common.clearSelection') }}
      </button>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <template v-if="confirmingAction">
        <span class="text-sm text-ink-700">
          {{ t('common.confirmBulkAction') }}
        </span>
        <BaseButton
          size="sm"
          :variant="
            confirmingAction.variant === 'danger' ? 'danger' : 'primary'
          "
          @click="runAction(confirmingAction)"
        >
          {{ t('common.confirm') }}
        </BaseButton>
        <BaseButton
          size="sm"
          variant="outline"
          @click="confirmingAction = null"
        >
          {{ t('common.cancel') }}
        </BaseButton>
      </template>
      <template v-else>
        <BaseButton
          v-for="action in actions"
          :key="action.key"
          size="sm"
          :variant="action.variant || 'outline'"
          :disabled="action.disabled || !!loadingKey"
          :loading="loadingKey === action.key"
          @click="requestAction(action)"
        >
          <component
            :is="action.icon"
            v-if="action.icon"
            :size="15"
            :stroke-width="2"
            aria-hidden="true"
          />
          {{ action.label }}
        </BaseButton>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import BaseButton from '@/components/ui/BaseButton.vue'

const props = defineProps({
  actions: {
    type: Array,
    required: true
  },
  loadingKey: {
    type: String,
    default: ''
  },
  selectedCount: {
    type: Number,
    required: true
  }
})

const emit = defineEmits(['action', 'clear'])

const { t } = useI18n()
const confirmingAction = ref(null)

function clearSelection() {
  confirmingAction.value = null
  emit('clear')
}

function requestAction(action) {
  if (action.confirm) {
    confirmingAction.value = action
    return
  }
  runAction(action)
}

function runAction(action) {
  confirmingAction.value = null
  emit('action', action.key)
}

watch(
  () => props.selectedCount,
  (count) => {
    if (!count) confirmingAction.value = null
  }
)
</script>
