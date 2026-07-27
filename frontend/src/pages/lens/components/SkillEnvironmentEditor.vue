<template>
  <FormRow :label="t('lensAdmin.skills.environmentVariables')">
    <div class="overflow-hidden rounded-lg border border-line bg-surface">
      <div
        class="flex items-center justify-between gap-3 border-b border-line bg-surface-sunken px-3 py-2.5"
      >
        <p class="text-sm leading-5 text-ink-600">
          {{ t('lensAdmin.skills.environmentVariablesHelp') }}
        </p>
        <BaseButton
          class="shrink-0"
          size="sm"
          variant="outline"
          @click="addEnvironment"
        >
          {{ t('common.add') }}
        </BaseButton>
      </div>
      <div v-if="!modelValue.length" class="px-3 py-4 text-sm text-ink-400">
        {{ t('lensAdmin.skills.noEnvironmentVariables') }}
      </div>
      <div
        v-for="(item, index) in modelValue"
        :key="index"
        class="grid grid-cols-1 items-center gap-2 border-b border-line p-3 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]"
      >
        <input
          :value="item.name"
          class="form-input min-w-0 font-mono font-medium tracking-tight"
          :pattern="SHELL_ENVIRONMENT_NAME_PATTERN"
          :aria-label="t('lensAdmin.skills.environmentKey')"
          :placeholder="t('lensAdmin.skills.environmentKey')"
          required
          @input="updateEnvironment(index, 'name', $event.target.value)"
        />
        <input
          :value="item.description"
          class="form-input min-w-0 font-sans"
          :aria-label="t('lensAdmin.skills.environmentDescription')"
          :placeholder="t('lensAdmin.skills.environmentDescription')"
          @input="updateEnvironment(index, 'description', $event.target.value)"
        />
        <button
          type="button"
          class="inline-flex h-9 w-9 items-center justify-center rounded-md text-danger-600 transition-colors hover:bg-danger-50 hover:text-danger-700"
          :aria-label="t('common.delete')"
          :title="t('common.delete')"
          @click="removeEnvironment(index)"
        >
          <MinusIcon class="h-4 w-4" />
        </button>
      </div>
    </div>
  </FormRow>
</template>

<script setup>
import { Minus as MinusIcon } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import BaseButton from '@/components/ui/BaseButton.vue'

import { SHELL_ENVIRONMENT_NAME_PATTERN } from '../skillEnvironment'
import FormRow from './FormRow.vue'

const { t } = useI18n()

const props = defineProps({
  modelValue: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['update:modelValue', 'change'])

function updateEnvironment(index, key, value) {
  const environment = props.modelValue.map((item, itemIndex) =>
    itemIndex === index ? { ...item, [key]: value } : item
  )
  emit('update:modelValue', environment)
  emit('change')
}

function addEnvironment() {
  emit('update:modelValue', [
    ...props.modelValue,
    {
      name: '',
      description: '',
      required: true,
      secret: false
    }
  ])
  emit('change')
}

function removeEnvironment(index) {
  emit(
    'update:modelValue',
    props.modelValue.filter((_, itemIndex) => itemIndex !== index)
  )
  emit('change')
}
</script>

<style scoped>
.form-input {
  @apply w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink-900 placeholder:text-ink-400 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}
</style>
