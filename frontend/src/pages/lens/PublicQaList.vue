<template>
  <div class="min-h-screen bg-surface-sunken">
    <PublicLensHeader
      :assistant-name="assistant?.name"
      :assistant-slug="assistant?.slug"
    />
    <main class="mx-auto max-w-3xl px-4 py-8">
      <BaseLoading v-if="loading && !items.length" />

      <div
        v-else-if="accessState"
      >
        <PublicQaAccessState
          :type="accessState"
          @login="goLogin"
          @home="goHome"
        />
      </div>

      <template v-else>
        <div class="mb-4 flex items-center justify-between gap-3">
          <h1 class="text-base font-semibold text-ink-900">
            {{ t('lens.qa.publicListCount', { count: total }) }}
          </h1>
        </div>

        <div
          v-if="!items.length"
          class="rounded-lg border border-line bg-surface-sunken py-16 text-center"
        >
          <p class="text-sm font-medium text-ink-500">
            {{ t('lens.qa.listEmpty') }}
          </p>
        </div>

        <div v-else class="space-y-3">
          <SharedQaCard
            v-for="item in items"
            :key="item.token"
            :item="item"
          />
        </div>

        <div v-if="nextOffset !== null" class="mt-5 text-center">
          <BaseButton
            variant="ghost"
            size="sm"
            :loading="loadingMore"
            @click="loadMore"
          >
            {{ t('lens.qa.loadMore') }}
          </BaseButton>
        </div>
      </template>
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import PublicLensHeader from '@/components/lens/PublicLensHeader.vue'
import PublicQaAccessState from '@/components/lens/PublicQaAccessState.vue'
import SharedQaCard from '@/components/lens/SharedQaCard.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import BaseButton from '@/components/ui/BaseButton.vue'
import { getPublicAssistantQa } from '@/api/lens'

const props = defineProps({ slug: { type: String, required: true } })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const PAGE_SIZE = 20
const assistant = ref(null)
const items = ref([])
const total = ref(0)
const nextOffset = ref(0)
const loading = ref(true)
const loadingMore = ref(false)
const accessState = ref(null)

function accessStateFromError(error) {
  const code = error?.response?.data?.code
  if (error?.response?.status === 403 && code === 'AUTHENTICATION_REQUIRED') {
    return 'login-required'
  }
  if (error?.response?.status === 403 && code === 'ASSISTANT_ACCESS_DENIED') {
    return 'forbidden'
  }
  return 'not-found'
}

async function load() {
  loading.value = true
  accessState.value = null
  items.value = []
  nextOffset.value = 0
  total.value = 0

  try {
    const data = await getPublicAssistantQa(props.slug, {
      limit: PAGE_SIZE,
      offset: 0
    })
    assistant.value = data?.assistant || null
    items.value = data?.results || []
    total.value = data?.total || 0
    nextOffset.value = data?.next_offset ?? null
  } catch (error) {
    accessState.value = accessStateFromError(error)
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (nextOffset.value === null) {
    return
  }
  loadingMore.value = true
  try {
    const data = await getPublicAssistantQa(props.slug, {
      limit: PAGE_SIZE,
      offset: nextOffset.value
    })
    items.value = items.value.concat(data?.results || [])
    nextOffset.value = data?.next_offset ?? null
  } finally {
    loadingMore.value = false
  }
}

function goLogin() {
  router.push({ path: '/login', query: { next: route.fullPath } })
}

function goHome() {
  router.push('/')
}

onMounted(load)
watch(() => props.slug, load)
</script>
