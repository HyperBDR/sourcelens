<template>
  <AppLayout>
    <div class="max-w-5xl mx-auto space-y-4">
      <!-- Page Header -->
      <div class="mb-3">
        <h2 class="text-lg font-semibold text-gray-900">
          {{ t('settings.profile.title') }}
        </h2>
        <p class="text-sm text-gray-600 mt-1">
          {{ t('settings.profile.subtitle') }}
        </p>
      </div>

      <!-- Loading State -->
      <BaseLoading v-if="loading" full-page size="lg" variant="primary" />

      <!-- Content -->
      <template v-else>
        <!-- User Profile Section -->
        <UserProfileSection />

        <!-- Basic Information Card -->
        <BasicInfoCard />
      </template>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUserStore } from '@/store/user'
import AppLayout from '@/components/layout/AppLayout.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import UserProfileSection from '@/components/settings/UserProfileSection.vue'
import BasicInfoCard from '@/components/settings/BasicInfoCard.vue'

const { t } = useI18n()
const userStore = useUserStore()
const loading = ref(true)

const loadUserData = async () => {
  loading.value = true
  try {
    if (!userStore.user) {
      await userStore.checkAuthStatus()
    }
  } catch (error) {
    console.error('Failed to load user data:', error)
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadUserData()
})
</script>
