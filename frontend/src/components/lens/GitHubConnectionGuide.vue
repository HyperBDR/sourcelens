<template>
  <aside
    class="self-start overflow-hidden rounded-xl border border-line bg-surface-sunken md:sticky md:top-0 md:max-h-[calc(100vh-10rem)] md:overflow-y-auto"
    aria-labelledby="github-connection-guide-title"
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
          id="github-connection-guide-title"
          class="text-sm font-semibold text-ink-900"
        >
          {{ t('lensAdmin.connections.githubGuideTitle') }}
        </h3>
        <p class="mt-0.5 text-xs leading-5 text-ink-500">
          {{ t('lensAdmin.connections.githubGuideSummary') }}
        </p>
      </div>
    </div>

    <ol class="space-y-4 px-4 py-4 text-sm text-ink-700">
      <li class="flex gap-2.5">
        <span class="github-guide-step">1</span>
        <div class="min-w-0">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.githubGuideCreateTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.githubGuideCreateHint') }}
          </p>
        </div>
      </li>

      <li class="flex gap-2.5">
        <span class="github-guide-step">2</span>
        <div class="min-w-0">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.githubGuideRepositoryTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.githubGuideRepositoryHint') }}
          </p>
        </div>
      </li>

      <li class="flex gap-2.5">
        <span class="github-guide-step">3</span>
        <div class="min-w-0 flex-1">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.githubGuidePermissionTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.githubGuidePermissionHint') }}
          </p>
          <ul class="mt-2 space-y-1.5">
            <li
              v-for="permission in permissions"
              :key="permission.name"
              class="flex items-start justify-between gap-2 rounded border border-line bg-surface px-2 py-1.5 text-xs"
            >
              <span class="font-medium text-ink-800">
                {{ permission.name }}
              </span>
              <span class="text-right text-ink-500">
                {{ t(permission.hint) }}
              </span>
            </li>
          </ul>
        </div>
      </li>

      <li class="flex gap-2.5">
        <span class="github-guide-step">4</span>
        <div class="min-w-0">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.githubGuideConnectTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.githubGuideConnectHint') }}
          </p>
        </div>
      </li>
    </ol>

    <nav
      class="space-y-2 border-t border-line bg-surface px-4 py-3 text-xs"
      :aria-label="t('lensAdmin.connections.githubGuideLinksLabel')"
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

const permissions = [
  {
    name: 'Contents',
    hint: 'lensAdmin.connections.githubGuideContentsPermission'
  },
  {
    name: 'Issues',
    hint: 'lensAdmin.connections.githubGuideIssuesPermission'
  },
  {
    name: 'Pull requests',
    hint: 'lensAdmin.connections.githubGuidePullsPermission'
  },
  {
    name: 'Actions',
    hint: 'lensAdmin.connections.githubGuideActionsPermission'
  }
]

const guideLinks = [
  {
    label: 'lensAdmin.connections.githubGuideCreateLink',
    href: 'https://github.com/settings/personal-access-tokens/new'
  },
  {
    label: 'lensAdmin.connections.githubGuideTokenDocsLink',
    href:
      'https://docs.github.com/en/authentication/' +
      'keeping-your-account-and-data-secure/' +
      'managing-your-personal-access-tokens'
  },
  {
    label: 'lensAdmin.connections.githubGuidePermissionDocsLink',
    href:
      'https://docs.github.com/en/rest/authentication/' +
      'permissions-required-for-fine-grained-personal-access-tokens'
  }
]
</script>

<style scoped>
.github-guide-step {
  @apply flex h-5 w-5 shrink-0 items-center justify-center rounded-full
    bg-brand-100 text-[11px] font-semibold text-brand-700;
}
</style>
