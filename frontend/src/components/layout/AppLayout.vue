<template>
  <div class="h-screen bg-gray-50 flex w-full overflow-hidden">
    <!-- Sidebar -->
    <AppSidebar
      v-if="resolvedShowSidebar"
      :show-mobile-menu="showMobileMenu"
      @close="showMobileMenu = false"
    />

    <!-- Main content area -->
    <div class="flex-1 flex flex-col min-w-0 w-0 h-full overflow-hidden">
      <!-- Header -->
      <AppHeader
        :show-menu-button="resolvedShowSidebar"
        @toggle-menu="showMobileMenu = !showMobileMenu"
      />

      <!-- Main content - scrollable -->
      <main
        class="flex-1 min-w-0 overflow-y-auto bg-gray-50"
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
