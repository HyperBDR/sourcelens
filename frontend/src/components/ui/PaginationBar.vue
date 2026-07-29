<template>
  <div
    v-if="total > 0"
    class="mt-4 flex flex-shrink-0 flex-col items-start justify-between gap-4 border-t border-gray-200 pt-4 md:flex-row md:items-center"
  >
    <div class="text-sm font-medium text-gray-700">
      {{ t('common.pagination.showing', showing) }}
    </div>
    <div
      class="flex w-full flex-col gap-3 md:w-auto md:flex-row md:items-center"
    >
      <div class="flex items-center gap-3">
        <label class="text-sm text-gray-600">
          {{ t('common.pagination.itemsPerPage') }}:
        </label>
        <select
          :value="pageSize"
          class="min-h-11 rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-primary-500 focus:outline-none focus:ring-1 focus:ring-primary-500 md:min-h-0"
          @change="updatePageSize"
        >
          <option v-for="size in pageSizeOptions" :key="size" :value="size">
            {{ size }}
          </option>
        </select>
      </div>
      <div
        class="grid w-full grid-cols-[2.75rem_1fr_2.75rem] items-center gap-2 md:flex md:w-auto md:gap-3"
      >
        <BaseButton
          variant="outline"
          size="sm"
          :disabled="currentPage <= 1"
          :title="t('common.pagination.previous')"
          @click="$emit('prev')"
        >
          <svg
            class="h-4 w-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M15 19l-7-7 7-7"
            />
          </svg>
          <span class="sr-only">{{ t('common.pagination.previous') }}</span>
        </BaseButton>
        <span
          class="inline-flex min-h-11 items-center justify-center rounded-md border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm font-semibold text-gray-700 md:min-h-0"
        >
          {{
            t('common.pagination.page', {
              current: currentPage,
              total: normalizedTotalPages
            })
          }}
        </span>
        <BaseButton
          variant="outline"
          size="sm"
          :disabled="currentPage >= normalizedTotalPages"
          :title="t('common.pagination.next')"
          @click="$emit('next')"
        >
          <svg
            class="h-4 w-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M9 5l7 7-7 7"
            />
          </svg>
          <span class="sr-only">{{ t('common.pagination.next') }}</span>
        </BaseButton>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import BaseButton from './BaseButton.vue'

const props = defineProps({
  currentPage: { type: Number, required: true },
  pageSize: { type: Number, required: true },
  total: { type: Number, required: true },
  pageSizeOptions: {
    type: Array,
    default: () => [10, 20, 50, 100]
  }
})

const emit = defineEmits([
  'update:pageSize',
  'prev',
  'next',
  'page-size-change'
])
const { t } = useI18n()

const normalizedTotalPages = computed(() =>
  Math.max(1, Math.ceil(props.total / props.pageSize))
)

const showing = computed(() => ({
  from: props.total === 0 ? 0 : (props.currentPage - 1) * props.pageSize + 1,
  to: Math.min(props.currentPage * props.pageSize, props.total),
  total: props.total
}))

function updatePageSize(event) {
  emit('update:pageSize', Number(event.target.value))
  emit('page-size-change')
}
</script>
