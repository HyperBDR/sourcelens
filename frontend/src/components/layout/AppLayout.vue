<template>
  <div class="flex h-screen w-full overflow-hidden bg-surface-sunken">
    <!-- Sidebar -->
    <AppSidebar
      v-if="resolvedShowSidebar"
      :show-mobile-menu="showMobileMenu"
      @close="showMobileMenu = false"
    />

    <!-- Main content area -->
    <div class="flex-1 flex min-w-0 flex-col overflow-hidden bg-surface">
      <!-- Header -->
      <AppHeader
        :show-menu-button="resolvedShowSidebar"
        @toggle-menu="showMobileMenu = !showMobileMenu"
      />

      <!-- Main content - scrollable -->
      <main
        class="flex-1 min-w-0 overflow-y-auto bg-surface-sunken"
        :class="
          resolvedShowSidebar ? 'py-3 px-4' : 'px-6 py-6 sm:px-8 lg:px-10'
        "
      >
        <div :key="route.path">
          <slot />
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from './AppHeader.vue'
import AppSidebar from './AppSidebar.vue'

const props = defineProps({
  showSidebar: {
    type: Boolean,
    default: true
  }
})

const route = useRoute()
const showMobileMenu = ref(false)
const resolvedShowSidebar = computed(() => props.showSidebar)
</script>
