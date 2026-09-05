<template>
  <aside
    class="self-start overflow-hidden rounded-xl border border-line bg-surface-sunken md:sticky md:top-0 md:max-h-[calc(100vh-10rem)] md:overflow-y-auto"
    aria-labelledby="feishu-connection-guide-title"
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
          id="feishu-connection-guide-title"
          class="text-sm font-semibold text-ink-900"
        >
          {{ t('lensAdmin.connections.feishuGuideTitle') }}
        </h3>
        <p class="mt-0.5 text-xs leading-5 text-ink-500">
          {{ t('lensAdmin.connections.feishuGuideSummary') }}
        </p>
      </div>
    </div>

    <ol class="space-y-4 px-4 py-4 text-sm text-ink-700">
      <li class="flex gap-2.5">
        <span class="feishu-guide-step">1</span>
        <div class="min-w-0">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.feishuGuideCreateTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.feishuGuideCreateHint') }}
          </p>
        </div>
      </li>

      <li class="flex gap-2.5">
        <span class="feishu-guide-step">2</span>
        <div class="min-w-0 flex-1">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.feishuGuidePermissionTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.feishuGuidePermissionHint') }}
          </p>
          <ul
            class="mt-2 grid grid-cols-2 gap-1.5"
            :aria-label="
              t('lensAdmin.connections.feishuGuidePermissionListLabel')
            "
          >
            <li v-for="permission in requiredPermissions" :key="permission">
              <code
                class="block break-all rounded border border-line bg-surface px-2 py-1 text-[11px] leading-4 text-ink-700"
              >
                {{ permission }}
              </code>
            </li>
          </ul>
        </div>
      </li>

      <li class="flex gap-2.5">
        <span class="feishu-guide-step">3</span>
        <div class="min-w-0">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.feishuGuideResourceTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.feishuGuideResourceHint') }}
          </p>
        </div>
      </li>

      <li class="flex gap-2.5">
        <span class="feishu-guide-step">4</span>
        <div class="min-w-0">
          <p class="font-medium text-ink-900">
            {{ t('lensAdmin.connections.feishuGuideConnectTitle') }}
          </p>
          <p class="mt-0.5 text-xs leading-5 text-ink-600">
            {{ t('lensAdmin.connections.feishuGuideConnectHint') }}
          </p>
        </div>
      </li>
    </ol>

    <nav
      class="space-y-2 border-t border-line bg-surface px-4 py-3 text-xs"
      :aria-label="t('lensAdmin.connections.feishuGuideLinksLabel')"
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

const requiredPermissions = [
  'drive:file:readonly',
  'drive:file:download',
  'drive:export:readonly',
  'docx:document:readonly',
  'docs:document.content:read',
  'docs:document.media:download',
  'docs:document:export',
  'space:document:retrieve',
  'wiki:wiki:readonly'
]

const guideLinks = [
  {
    label: 'lensAdmin.connections.feishuGuideOpenPlatformLink',
    href: 'https://open.feishu.cn/app'
  },
  {
    label: 'lensAdmin.connections.feishuGuideDataPermissionLink',
    href:
      'https://open.feishu.cn/document/api-call-guide/calling-process/' +
      'configure-app-data-permissions'
  },
  {
    label: 'lensAdmin.connections.feishuGuideApiPermissionLink',
    href:
      'https://open.feishu.cn/document/server-docs/application-scope/' +
      'scope-list'
  }
]
</script>

<style scoped>
.feishu-guide-step {
  @apply flex h-5 w-5 shrink-0 items-center justify-center rounded-full
    bg-brand-100 text-[11px] font-semibold text-brand-700;
}
</style>
