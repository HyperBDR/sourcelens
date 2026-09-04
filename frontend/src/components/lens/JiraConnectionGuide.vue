<template>
  <aside
    class="self-start overflow-hidden rounded-xl border border-line bg-surface-sunken md:sticky md:top-0 md:max-h-[calc(100vh-10rem)] md:overflow-y-auto"
    aria-labelledby="jira-connection-guide-title"
  >
    <div
      class="flex items-start gap-3 border-b border-line bg-surface px-4 py-3"
    >
      <span
        class="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand-100 text-brand-700"
        aria-hidden="true"
      >
        <BookOpen :size="17" />
      </span>
      <div class="min-w-0">
        <h3
          id="jira-connection-guide-title"
          class="text-sm font-semibold text-ink-900"
        >
          {{ t('lensAdmin.connections.jiraGuideTitle') }}
        </h3>
        <p class="mt-0.5 text-xs leading-5 text-ink-500">
          {{ t('lensAdmin.connections.jiraGuideSummary') }}
        </p>
      </div>
    </div>

    <ol class="space-y-4 px-4 py-4 text-sm text-ink-700">
      <li class="flex gap-2.5">
        <span class="jira-guide-step">1</span>
        <div class="min-w-0">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.jiraGuideEndpointTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.jiraGuideEndpointHint') }}
          </p>
          <div class="mt-2 flex flex-wrap gap-1.5">
            <code
              v-for="deployment in deployments"
              :key="deployment"
              class="rounded border border-line bg-surface px-2 py-1 text-[11px] text-ink-700"
            >
              {{ deployment }}
            </code>
          </div>
        </div>
      </li>

      <li class="flex gap-2.5">
        <span class="jira-guide-step">2</span>
        <div class="min-w-0">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.jiraGuideCredentialTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.jiraGuideCredentialHint') }}
          </p>
        </div>
      </li>

      <li class="flex gap-2.5">
        <span class="jira-guide-step">3</span>
        <div class="min-w-0">
          <p class="font-medium text-ink-900">Browse projects</p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.jiraGuideProjectHint') }}
          </p>
        </div>
      </li>

      <li class="flex gap-2.5">
        <span class="jira-guide-step">4</span>
        <div class="min-w-0">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.jiraGuideBoundaryTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.jiraGuideBoundaryHint') }}
          </p>
        </div>
      </li>
    </ol>

    <nav
      class="space-y-2 border-t border-line bg-surface px-4 py-3 text-xs"
      :aria-label="t('lensAdmin.connections.jiraGuideLinksLabel')"
    >
      <a
        v-for="link in guideLinks"
        :key="link.href"
        class="flex items-center justify-between gap-2 font-medium text-brand-700 hover:text-brand-800 hover:underline"
        :href="link.href"
        target="_blank"
        rel="noopener noreferrer"
      >
        <span>{{ t(link.label) }}</span>
        <ExternalLink :size="13" class="shrink-0" aria-hidden="true" />
      </a>
    </nav>
  </aside>
</template>

<script setup>
import { BookOpen, ExternalLink } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

const deployments = ['Jira Cloud', 'self-hosted Jira']

const guideLinks = [
  {
    label: 'lensAdmin.connections.jiraGuideCreateTokenLink',
    href: 'https://id.atlassian.com/manage-profile/security/api-tokens'
  },
  {
    label: 'lensAdmin.connections.jiraGuideAuthDocsLink',
    href:
      'https://developer.atlassian.com/cloud/jira/platform/' +
      'basic-auth-for-rest-apis/'
  }
]
</script>

<style scoped>
.jira-guide-step {
  @apply flex h-5 w-5 shrink-0 items-center justify-center rounded-full
    bg-brand-100 text-[11px] font-semibold text-brand-700;
}
</style>
