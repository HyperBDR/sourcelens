import { existsSync, statSync, createReadStream } from 'fs'
import { resolve, extname, normalize, join, sep } from 'path'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Directory holding static design/prototype pages for review.
const DESIGN_DIR = resolve(__dirname, 'design')

// Minimal MIME map for static design assets.
const MIME_TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf'
}

/**
 * Dev-only plugin serving static design pages under /design.
 *
 * Active only in `vite serve` (dev). The design directory lives outside
 * src/public, so production builds never include these review pages.
 */
function designPagesPlugin() {
  return {
    name: 'design-pages-dev',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use('/design', (req, res) => {
        const urlPath = decodeURIComponent((req.url || '/').split('?')[0])
        let target = normalize(join(DESIGN_DIR, urlPath))

        // Block path traversal outside the design directory.
        if (target !== DESIGN_DIR && !target.startsWith(DESIGN_DIR + sep)) {
          res.statusCode = 403
          res.end('Forbidden')
          return
        }

        if (existsSync(target) && statSync(target).isDirectory()) {
          target = join(target, 'index.html')
        }

        if (!existsSync(target) || !statSync(target).isFile()) {
          res.statusCode = 404
          res.end('Not Found')
          return
        }

        res.setHeader(
          'Content-Type',
          MIME_TYPES[extname(target).toLowerCase()] ||
            'application/octet-stream'
        )
        createReadStream(target).pipe(res)
      })
    }
  }
}

export default defineConfig({
  plugins: [vue(), designPagesPlugin()],
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
    // Hosts allowed to reach the dev server (e.g. external/tunnel domains).
    // Defaults to the company domain; extend via VITE_ALLOWED_HOSTS
    // (comma-separated) without editing this file.
    allowedHosts: [
      '.oneprocloud.com.cn',
      ...(process.env.VITE_ALLOWED_HOSTS || '')
        .split(',')
        .map((host) => host.trim())
        .filter(Boolean)
    ],
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
