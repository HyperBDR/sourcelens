<template>
  <div class="min-h-screen bg-surface-sunken">
    <PublicLensHeader
      :assistant-name="qa?.assistant_name"
      :assistant-slug="qa?.assistant_slug"
      :show-qa-link="true"
    />
    <main class="mx-auto max-w-3xl px-4 py-8">
      <BaseLoading v-if="loading" />

      <div
        v-else-if="notFound"
        class="rounded-lg border border-line bg-surface py-16 text-center"
      >
        <p class="text-sm font-medium text-ink-500">
          {{ t('lens.qa.notFound') }}
        </p>
      </div>

      <article v-else-if="qa">
        <router-link
          v-if="qa.assistant_slug"
          :to="`/lens/assistants/${qa.assistant_slug}/qa`"
          class="text-xs font-medium text-ink-500 no-underline hover:text-primary-600"
        >
          {{ qa.assistant_name }}
        </router-link>

        <h1
          class="mt-3 whitespace-pre-wrap rounded-lg border border-line bg-surface px-4 py-3 text-lg font-semibold text-ink-900"
        >
          {{ qa.title || qa.question }}
        </h1>

        <div class="mt-5">
          <MarkdownRenderer :content="qa.answer || ''" />
        </div>

        <div
          class="mt-6 flex items-center justify-between border-t border-line pt-4 text-xs text-ink-400"
        >
          <div class="flex items-center gap-3">
            <span>{{ formatDate(qa.published_at, 'yyyy-MM-dd HH:mm') }}</span>
            <span>{{ t('lens.qa.viewCount', { count: qa.view_count }) }}</span>
          </div>
          <button
            type="button"
            class="inline-flex items-center gap-1 rounded-md px-2 py-1 text-ink-500 transition-colors hover:bg-surface-sunken hover:text-primary-600"
            @click="copyLink"
          >
            <Copy :size="14" :stroke-width="2" aria-hidden="true" />
            {{ t('lens.share.copyLink') }}
          </button>
        </div>

        <div
          v-if="qa.assistant_slug"
          class="mt-8 rounded-xl border border-line bg-surface px-5 py-4"
        >
          <p class="text-sm font-medium text-ink-700">
            {{ t('lens.qa.ctaTitle') }}
          </p>
          <router-link
            :to="`/lens/assistants/${qa.assistant_slug}/chat`"
            class="mt-2 inline-block text-sm font-medium text-primary-600 no-underline hover:text-primary-700"
          >
            {{ t('lens.qa.ctaAction', { name: qa.assistant_name }) }} →
          </router-link>
        </div>
      </article>
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Copy } from '@lucide/vue'

import PublicLensHeader from '@/components/lens/PublicLensHeader.vue'
import MarkdownRenderer from '@/components/ui/MarkdownRenderer.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import { getPublicQa } from '@/api/lens'
import { copyToClipboard } from '@/utils/clipboard'
import { formatDate } from '@/utils/formatting'
import { qaShareUrl } from '@/utils/lens'
import { useToast } from '@/composables/useToast'

const props = defineProps({ token: { type: String, required: true } })

const { t } = useI18n()
const { showSuccess, showError } = useToast()

const qa = ref(null)
const loading = ref(true)
const notFound = ref(false)

async function load() {
  loading.value = true
  notFound.value = false
  try {
    qa.value = await getPublicQa(props.token)
    const title = qa.value?.title || qa.value?.question
    if (title) {
      document.title = title
    }
  } catch {
    qa.value = null
    notFound.value = true
  } finally {
    loading.value = false
  }
}

async function copyLink() {
  if (await copyToClipboard(qaShareUrl(props.token))) {
    showSuccess(t('lens.qa.copied'))
  } else {
    showError(t('lens.qa.copyFailed'))
  }
}

onMounted(load)
watch(() => props.token, load)
</script>
