<template>
  <div class="flex flex-wrap items-center gap-2">
    <template v-if="confirming">
      <BaseButton size="sm" variant="danger" @click="confirmDelete">
        {{ t('common.confirm') }}
      </BaseButton>
      <BaseButton size="sm" variant="outline" @click="confirming = false">
        {{ t('common.cancel') }}
      </BaseButton>
    </template>
    <template v-else>
      <BaseButton size="sm" variant="outline" @click="$emit('edit', row)">
        {{ t('common.edit') }}
      </BaseButton>
      <BaseButton size="sm" variant="danger" @click="confirming = true">
        {{ t('common.delete') }}
      </BaseButton>
    </template>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import BaseButton from '@/components/ui/BaseButton.vue'

const props = defineProps({
  row: {
    type: Object,
    required: true
  }
})
const emit = defineEmits(['edit', 'delete'])

const { t } = useI18n()
const confirming = ref(false)

function confirmDelete() {
  confirming.value = false
  emit('delete', props.row)
}
</script>
