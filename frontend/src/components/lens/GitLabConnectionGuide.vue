<template>
  <aside
    class="self-start overflow-hidden rounded-xl border border-line bg-surface-sunken md:sticky md:top-0 md:max-h-[calc(100vh-10rem)] md:overflow-y-auto"
    aria-labelledby="gitlab-connection-guide-title"
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
          id="gitlab-connection-guide-title"
          class="text-sm font-semibold text-ink-900"
        >
          {{ t('lensAdmin.connections.gitlabGuideTitle') }}
        </h3>
        <p class="mt-0.5 text-xs leading-5 text-ink-500">
          {{ t('lensAdmin.connections.gitlabGuideSummary') }}
        </p>
      </div>
    </div>

    <ol class="space-y-4 px-4 py-4 text-sm text-ink-700">
      <li class="flex gap-2.5">
        <span class="gitlab-guide-step">1</span>
        <div class="min-w-0">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.gitlabGuideEndpointTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.gitlabGuideEndpointHint') }}
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
        <span class="gitlab-guide-step">2</span>
        <div class="min-w-0 flex-1">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.gitlabGuideTokenTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.gitlabGuideTokenHint') }}
          </p>
          <ul class="mt-2 space-y-1.5">
            <li
              v-for="scope in scopes"
              :key="scope.name"
              class="flex items-start justify-between gap-2 rounded border border-line bg-surface px-2 py-1.5 text-xs"
            >
              <code class="font-medium text-ink-800">
                {{ scope.name }}
              </code>
              <span class="text-right text-ink-500">
                {{ t(scope.hint) }}
              </span>
            </li>
          </ul>
        </div>
      </li>

      <li class="flex gap-2.5">
        <span class="gitlab-guide-step">3</span>
        <div class="min-w-0">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.gitlabGuideProjectTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.gitlabGuideProjectHint') }}
          </p>
        </div>
      </li>

      <li class="flex gap-2.5">
        <span class="gitlab-guide-step">4</span>
        <div class="min-w-0">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.gitlabGuideBoundaryTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.gitlabGuideBoundaryHint') }}
          </p>
        </div>
      </li>
    </ol>

    <nav
      class="space-y-2 border-t border-line bg-surface px-4 py-3 text-xs"
      :aria-label="t('lensAdmin.connections.gitlabGuideLinksLabel')"
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

const deployments = ['GitLab.com', 'self-managed GitLab']

const scopes = [
  {
    name: 'read_api',
    hint: 'lensAdmin.connections.gitlabGuideApiScope'
  },
  {
    name: 'read_repository',
    hint: 'lensAdmin.connections.gitlabGuideRepositoryScope'
  }
]

const guideLinks = [
  {
    label: 'lensAdmin.connections.gitlabGuideTokenDocsLink',
    href: 'https://docs.gitlab.com/user/profile/personal_access_tokens/'
  },
  {
    label: 'lensAdmin.connections.gitlabGuideScopeDocsLink',
    href: 'https://docs.gitlab.com/security/tokens/access_token_scopes/'
  },
  {
    label: 'lensAdmin.connections.gitlabGuideAuthDocsLink',
    href: 'https://docs.gitlab.com/api/rest/authentication/'
  }
]
</script>

<style scoped>
.gitlab-guide-step {
  @apply flex h-5 w-5 shrink-0 items-center justify-center rounded-full
    bg-brand-100 text-[11px] font-semibold text-brand-700;
}
</style>
