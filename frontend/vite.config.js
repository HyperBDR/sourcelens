import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src')
    }
  },
  define: {
    // vue-i18n feature flags for better tree-shaking
    __VUE_I18N_FULL_INSTALL__: true,
    __VUE_I18N_LEGACY_API__: false,
    __INTLIFY_PROD_DEVTOOLS__: false
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // Vendor chunks
          'vue-vendor': ['vue', 'vue-router', 'pinia', 'vue-i18n'],
          // UI components chunk
          'ui-components': [
            '@/components/ui/BaseButton.vue',
            '@/components/ui/BaseInput.vue',
            '@/components/ui/BaseLoading.vue',
            '@/components/ui/StatusBadge.vue'
          ]
        },
        // Optimize chunk file names
        chunkFileNames: 'assets/js/[name]-[hash].js',
        entryFileNames: 'assets/js/[name]-[hash].js',
        assetFileNames: 'assets/[ext]/[name]-[hash].[ext]'
      }
    },
    // Increase chunk size warning limit
    chunkSizeWarningLimit: 1000,
    // Enable source maps for production debugging (optional)
    sourcemap: false,
    // Optimize for production (use esbuild minifier by default, faster than terser)
    minify: 'esbuild'
  },
  server: {
    // Listen on all interfaces for Docker / remote access
    host: '0.0.0.0',
    port: 3000,
    hmr: {
      overlay: false
    },
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        configure:
          process.env.VITE_DEBUG_PROXY === 'true'
            ? (proxy) => {
                proxy.on('error', (err) => {
                  console.warn('Proxy error', err)
                })
                proxy.on('proxyReq', (proxyReq, req) => {
                  console.log('Proxy request:', req.method, req.url)
                })
                proxy.on('proxyRes', (proxyRes, req) => {
                  console.log('Proxy response:', proxyRes.statusCode, req.url)
                })
              }
            : undefined
      },
      '/accounts': {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:8000',
        changeOrigin: true,
        secure: false
      }
    }
  }
})
