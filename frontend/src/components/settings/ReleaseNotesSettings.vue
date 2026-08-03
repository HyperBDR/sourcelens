<template>
  <div class="space-y-5">
    <div
      class="flex flex-wrap items-start justify-between gap-4 rounded-xl border border-line bg-gray-50 px-4 py-3"
    >
      <div>
        <p class="text-xs font-medium uppercase tracking-wide text-gray-500">
          {{ t('settings.releaseNotes.currentVersion') }}
        </p>
        <p class="mt-1 text-lg font-semibold text-gray-900">
          SourceLens {{ manifest.version }}
        </p>
      </div>
      <div class="text-right">
        <p class="text-xs font-medium uppercase tracking-wide text-gray-500">
          {{ t('settings.releaseNotes.releaseDate') }}
        </p>
        <p class="mt-1 text-sm font-medium text-gray-800">
          {{ manifest.releaseDate || '—' }}
        </p>
      </div>
    </div>

    <div v-if="groups.length" class="space-y-5">
      <section
        v-for="group in groups"
        :key="group.type"
        :aria-labelledby="`release-notes-${group.type}`"
      >
        <div class="mb-2 flex items-center justify-between gap-3">
          <h3
            :id="`release-notes-${group.type}`"
            class="inline-flex rounded-md px-2 py-1 text-xs font-semibold"
            :class="categoryStyles[group.type].badge"
          >
            {{ t(`settings.releaseNotes.categories.${group.type}`) }}
          </h3>
          <span class="text-xs text-gray-400">
            {{
              t('settings.releaseNotes.entryCount', {
                count: group.entries.length
              })
            }}
          </span>
        </div>
        <ul class="space-y-2">
          <li
            v-for="(entry, index) in group.entries"
            :key="`${group.type}-${entry.audience}-${index}`"
            class="border-l-2 bg-white py-2 pl-3 pr-2 text-sm leading-6 text-gray-700"
            :class="categoryStyles[group.type].border"
          >
            <span class="sr-only">
              {{ t(`settings.releaseNotes.categories.${group.type}`) }}:
            </span>
            <span
              v-if="entry.audience === 'admin'"
              class="mr-2 inline-flex rounded bg-gray-100 px-1.5 py-0.5 text-xs font-medium text-gray-600"
            >
              {{ t('settings.releaseNotes.adminOnly') }}
            </span>
            {{ entry.text }}
          </li>
        </ul>
      </section>
    </div>

    <p
      v-else
      class="rounded-xl border border-dashed border-line px-4 py-8 text-center text-sm text-gray-500"
    >
      {{ t('settings.releaseNotes.empty') }}
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import manifest from '@/generated/release-notes.json'
import { useUserStore } from '@/store/user'
import { selectLocalizedReleaseNotes } from '@/utils/releaseNotes'

const { locale, t } = useI18n()
const userStore = useUserStore()
const isAdmin = computed(() => userStore.userHasFeature('admin_console'))

const categoryStyles = {
  feature: {
    badge: 'bg-emerald-50 text-emerald-700',
    border: 'border-emerald-300'
  },
  improvement: {
    badge: 'bg-blue-50 text-blue-700',
    border: 'border-blue-300'
  },
  fix: {
    badge: 'bg-amber-50 text-amber-700',
    border: 'border-amber-300'
  }
}

const groups = computed(() =>
  selectLocalizedReleaseNotes(manifest, locale.value, isAdmin.value)
)
</script>
