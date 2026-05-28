<template>
  <AppLayout>
    <div class="w-full min-h-full flex flex-col">
      <!-- Hero: full-width strip, fills top -->
      <header
        class="w-full bg-white border-b border-gray-200 rounded-t-xl shadow-sm mb-6"
      >
        <div class="px-6 py-10 sm:py-12">
          <h1
            class="text-3xl sm:text-4xl font-bold text-gray-900 tracking-tight"
          >
            {{ t('common.appName') }}
          </h1>
          <p class="mt-3 text-lg sm:text-xl text-gray-700 max-w-2xl">
            {{ t('dashboard.overview.tagline') }}
          </p>
          <p class="mt-2 text-sm text-gray-500 max-w-xl">
            {{ t('dashboard.overview.subtagline') }}
          </p>
        </div>
      </header>

      <!-- Pillars: full width, two equal cards -->
      <section class="w-full mb-6" aria-label="Product pillars">
        <div class="grid grid-cols-1 gap-6">
          <div
            class="bg-white border border-gray-200 rounded-xl p-6 sm:p-8 shadow-sm"
          >
            <h2 class="text-lg font-semibold text-gray-900 mb-2">
              {{ t('dashboard.overview.pillarRnd') }}
            </h2>
            <p class="text-sm text-gray-600 leading-relaxed">
              {{ t('dashboard.overview.pillarRndDesc') }}
            </p>
          </div>
        </div>
      </section>

      <!-- Platform highlights: full width, four equal blocks -->
      <section class="w-full mb-6" aria-label="Platform capabilities">
        <h2
          class="text-sm font-medium text-gray-500 uppercase tracking-wider mb-4"
        >
          {{ t('dashboard.overview.highlightsTitle') }}
        </h2>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div class="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
            <div
              class="w-10 h-10 rounded-lg bg-primary-50 flex items-center justify-center mb-3"
            >
              <svg
                class="w-5 h-5 text-primary-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                />
              </svg>
            </div>
            <h3 class="text-base font-medium text-gray-900">
              {{ t('dashboard.overview.highlightAi') }}
            </h3>
            <p class="mt-1 text-sm text-gray-600">
              {{ t('dashboard.overview.highlightAiDesc') }}
            </p>
          </div>
          <div class="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
            <div
              class="w-10 h-10 rounded-lg bg-primary-50 flex items-center justify-center mb-3"
            >
              <svg
                class="w-5 h-5 text-primary-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z"
                />
              </svg>
            </div>
            <h3 class="text-base font-medium text-gray-900">
              {{ t('dashboard.overview.highlightMultiCloud') }}
            </h3>
            <p class="mt-1 text-sm text-gray-600">
              {{ t('dashboard.overview.highlightMultiCloudDesc') }}
            </p>
          </div>
          <div class="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
            <div
              class="w-10 h-10 rounded-lg bg-primary-50 flex items-center justify-center mb-3"
            >
              <svg
                class="w-5 h-5 text-primary-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M4 5a1 1 0 011-1h14a1 1 0 011 1v2a1 1 0 01-1 1H5a1 1 0 01-1-1V5zM4 13a1 1 0 011-1h6a1 1 0 011 1v6a1 1 0 01-1 1H5a1 1 0 01-1-1v-6zM16 13a1 1 0 011-1h2a1 1 0 011 1v6a1 1 0 01-1 1h-2a1 1 0 01-1-1v-6z"
                />
              </svg>
            </div>
            <h3 class="text-base font-medium text-gray-900">
              {{ t('dashboard.overview.highlightPlatform') }}
            </h3>
            <p class="mt-1 text-sm text-gray-600">
              {{ t('dashboard.overview.highlightPlatformDesc') }}
            </p>
          </div>
          <div class="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
            <div
              class="w-10 h-10 rounded-lg bg-primary-50 flex items-center justify-center mb-3"
            >
              <svg
                class="w-5 h-5 text-primary-600"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"
                />
              </svg>
            </div>
            <h3 class="text-base font-medium text-gray-900">
              {{ t('dashboard.overview.highlightSecure') }}
            </h3>
            <p class="mt-1 text-sm text-gray-600">
              {{ t('dashboard.overview.highlightSecureDesc') }}
            </p>
          </div>
        </div>
      </section>

      <!-- Product modules: full width cards -->
      <section class="w-full mb-6 flex-1" aria-label="Product modules">
        <h2
          class="text-sm font-medium text-gray-500 uppercase tracking-wider mb-4"
        >
          {{ t('dashboard.overview.modulesTitle') }}
        </h2>
        <div class="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
          <div
            class="flex flex-col bg-white border border-gray-200 rounded-xl p-6"
          >
            <span class="text-xs font-medium text-gray-400">{{
              t('dashboard.overview.comingSoon')
            }}</span>
            <h3 class="mt-2 text-base font-semibold text-gray-900">
              {{ t('dashboard.overview.moduleHyperMotion') }}
            </h3>
            <p class="mt-2 text-sm text-gray-600 flex-1">
              {{ t('dashboard.overview.moduleHyperMotionDesc') }}
            </p>
          </div>
          <div
            class="flex flex-col bg-white border border-gray-200 rounded-xl p-6"
          >
            <span class="text-xs font-medium text-gray-400">{{
              t('dashboard.overview.comingSoon')
            }}</span>
            <h3 class="mt-2 text-base font-semibold text-gray-900">
              {{ t('dashboard.overview.moduleRndAnalytics') }}
            </h3>
            <p class="mt-2 text-sm text-gray-600 flex-1">
              {{ t('dashboard.overview.moduleRndAnalyticsDesc') }}
            </p>
          </div>
          <div
            class="flex flex-col bg-white border border-gray-200 rounded-xl p-6"
          >
            <span class="text-xs font-medium text-gray-400">{{
              t('dashboard.overview.comingSoon')
            }}</span>
            <h3 class="mt-2 text-base font-semibold text-gray-900">
              {{ t('dashboard.overview.moduleCodeReview') }}
            </h3>
            <p class="mt-2 text-sm text-gray-600 flex-1">
              {{ t('dashboard.overview.moduleCodeReviewDesc') }}
            </p>
          </div>
        </div>
      </section>

      <!-- Footer strip: full width, subtle -->
      <footer class="w-full mt-auto pt-4 pb-2 border-t border-gray-200">
        <p class="text-sm text-gray-500 text-center">
          {{ t('dashboard.overview.moreComing') }}
        </p>
      </footer>
    </div>
  </AppLayout>
</template>

<script setup>
import { useI18n } from 'vue-i18n'
import AppLayout from '@/components/layout/AppLayout.vue'

const { t } = useI18n()
</script>
