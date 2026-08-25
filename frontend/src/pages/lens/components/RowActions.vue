<template>
  <div class="flex flex-wrap items-center justify-end gap-2">
    <template v-if="confirming">
      <BaseButton size="sm" variant="danger" @click="confirmDelete">
        {{ t('common.confirm') }}
      </BaseButton>
      <BaseButton size="sm" variant="outline" @click="confirming = false">
        {{ t('common.cancel') }}
      </BaseButton>
    </template>
    <RowActionMenu v-else :actions="actions" @select="handleAction" />
  </div>
</template>

<script setup>
import { Download, Pencil, Trash2 } from '@lucide/vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import BaseButton from '@/components/ui/BaseButton.vue'
import RowActionMenu from '@/components/ui/RowActionMenu.vue'

const props = defineProps({
  row: {
    type: Object,
    required: true
  },
  confirmInline: {
    type: Boolean,
    default: true
  }
})
const emit = defineEmits(['download', 'edit', 'delete'])

const { t } = useI18n()
const confirming = ref(false)

const actions = computed(() => [
  {
    key: 'download',
    label: t('lensAdmin.skills.download'),
    icon: Download
  },
  {
    key: 'edit',
    label: t('common.edit'),
    icon: Pencil
  },
  {
    key: 'delete',
    label: t('common.delete'),
    icon: Trash2,
    variant: 'danger',
    divider: true
  }
])

function confirmDelete() {
  confirming.value = false
  emit('delete', props.row)
}

function requestDelete() {
  if (props.confirmInline) {
    confirming.value = true
    return
  }
  emit('delete', props.row)
}

function handleAction(action) {
  if (action === 'download') {
    emit('download', props.row)
    return
  }
  if (action === 'edit') {
    emit('edit', props.row)
    return
  }
  requestDelete()
}
</script>
