<template>
  <header
    class="flex items-center justify-between gap-3 border-b border-line bg-surface px-4 py-3 sm:px-6"
  >
    <router-link to="/" class="flex items-center no-underline">
      <BrandLogo variant="responsive" />
    </router-link>
    <div class="flex items-center gap-2">
      <router-link
        v-if="showQaLink && assistantSlug"
        :to="`/lens/assistants/${assistantSlug}/qa`"
        class="inline-flex items-center gap-1.5 rounded-md border border-line px-3 py-1.5 text-sm font-medium text-theme-secondary no-underline transition-colors hover:border-line-strong hover:bg-surface-sunken hover:text-theme"
      >
        <MessagesSquare :size="15" :stroke-width="2" aria-hidden="true" />
        {{ t('lens.qa.publicListLink') }}
      </router-link>
      <router-link
        v-if="assistantSlug"
        :to="`/lens/assistants/${assistantSlug}/chat`"
        class="rounded-md bg-primary-600 px-3 py-1.5 text-sm font-medium text-white no-underline transition-colors hover:bg-primary-700"
      >
        {{ ctaLabel }}
      </router-link>
      <router-link
        v-if="!isAuthenticated"
        :to="loginTarget"
        class="rounded-md px-3 py-1.5 text-sm font-medium text-theme-secondary no-underline transition-colors hover:bg-surface-sunken"
      >
        {{ t('auth.signIn') }}
      </router-link>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { MessagesSquare } from '@lucide/vue'

import BrandLogo from '@/components/layout/BrandLogo.vue'
import { useUserStore } from '@/store/user'

const props = defineProps({
  assistantName: { type: String, default: '' },
  assistantSlug: { type: String, default: '' },
  showQaLink: { type: Boolean, default: false }
})

const { t } = useI18n()
const route = useRoute()
const userStore = useUserStore()
const isAuthenticated = computed(() => userStore.isAuthenticated)
const loginTarget = computed(() => ({
  path: '/login',
  query: { next: route.fullPath }
}))
const ctaLabel = computed(() =>
  props.assistantName
    ? t('lens.qa.ctaAction', { name: props.assistantName })
    : t('lens.qa.backToChat')
)
</script>
