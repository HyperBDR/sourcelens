<template>
  <div class="flex min-h-screen items-center justify-center bg-surface-sunken">
    <BaseLoading />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'

import BaseLoading from '@/components/ui/BaseLoading.vue'
import { useLensStore } from '@/store/lens'

const router = useRouter()
const lensStore = useLensStore()

async function redirectToChat() {
  try {
    const assistants = await lensStore.loadAssistants()
    const nextAssistant = assistants.find(
      (assistant) => assistant?.slug && assistant.status === 'active'
    ) || assistants.find((assistant) => assistant?.slug)

    if (nextAssistant?.slug) {
      await router.replace(`/lens/assistants/${nextAssistant.slug}/chat`)
      return
    }
  } catch {
    // Fall through to the home route below.
  }

  // No assistant to enter (e.g. none created yet) — let the smart home
  // route to the create-first-assistant guide.
  await router.replace('/')
}

onMounted(() => {
  void redirectToChat()
})
</script>
