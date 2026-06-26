<template>
  <div class="layout-admin flex h-screen w-full overflow-hidden bg-ink-50">
    <AdminSidebar
      :show-mobile-menu="showMobileMenu"
      @close="showMobileMenu = false"
    />
    <div class="flex-1 flex min-w-0 flex-col overflow-hidden bg-ink-50">
      <AdminHeader @toggle-menu="showMobileMenu = !showMobileMenu" />
      <main class="flex-1 min-w-0 overflow-y-auto bg-ink-50 px-4 py-3">
        <div :key="route.path" class="h-full min-h-0">
          <slot />
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute } from 'vue-router'
import AdminHeader from './AdminHeader.vue'
import AdminSidebar from './AdminSidebar.vue'

const showMobileMenu = ref(false)
const route = useRoute()
</script>
