<template>
  <div class="home-shell">
    <div v-if="loading" class="home-loading">
      <BaseLoading />
    </div>
    <AssistantEmptyState v-else :variant="variant" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import AssistantEmptyState from '@/components/lens/AssistantEmptyState.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import { useUserStore } from '@/store/user'
import { listAssistants } from '@/api/lens'

const router = useRouter()
const userStore = useUserStore()

const loading = ref(true)
const variant = ref('visitor')

function pickAssistant(list) {
  const active = list.find((item) => item.status === 'active')
  return active || list[0] || null
}

onMounted(async () => {
  // The router guard guarantees an authenticated user here. Admins resolve a
  // default assistant and enter its chat; with none, they see the
  // create-first-assistant guide. Regular end-users enter via shared links,
  // so the bare home only shows the no-assistant notice.
  if (userStore.userHasFeature('admin_console')) {
    try {
      const assistants = await listAssistants()
      const target = pickAssistant(assistants || [])
      if (target) {
        await router.replace(`/lens/assistants/${target.slug}/chat`)
        return
      }
    } catch {
      // Fall through to the create-first-assistant guide.
    }
    variant.value = 'admin'
  } else {
    variant.value = 'visitor'
  }
  loading.value = false
})
</script>

<style scoped>
.home-shell {
  @apply h-screen w-full bg-surface;
}

.home-loading {
  @apply flex h-full w-full items-center justify-center;
}
</style>
