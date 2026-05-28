<template>
  <div class="markdown-content prose max-w-none" v-html="renderedContent"></div>
</template>

<script setup>
import { computed } from 'vue'
import { marked } from 'marked'
import hljs from 'highlight.js/lib/core'
import { sanitizeHtml, escapeHtml } from '@/utils/sanitize'

// Import common languages for syntax highlighting
import javascript from 'highlight.js/lib/languages/javascript'
import python from 'highlight.js/lib/languages/python'
import bash from 'highlight.js/lib/languages/bash'
import json from 'highlight.js/lib/languages/json'
import xml from 'highlight.js/lib/languages/xml'

// Register languages
hljs.registerLanguage('javascript', javascript)
hljs.registerLanguage('python', python)
hljs.registerLanguage('bash', bash)
hljs.registerLanguage('json', json)
hljs.registerLanguage('xml', xml)

const props = defineProps({
  content: {
    type: String,
    default: ''
  },
  enableHighlight: {
    type: Boolean,
    default: true
  }
})

// Configure marked options
marked.setOptions({
  highlight: function (code, lang) {
    if (props.enableHighlight && lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(code, { language: lang }).value
      } catch (err) {
        // Silently fall back to plain text if highlighting fails
      }
    }
    return code
  },
  breaks: true,
  gfm: true
})

const renderedContent = computed(() => {
  if (!props.content) return ''

  try {
    let markdown = props.content.replace(/\r\n/g, '\n').replace(/\r/g, '\n')

    // Convert relative image paths to absolute URLs
    // Always use local HTTP service, never object storage URLs
    // Match markdown image syntax: ![alt](path)
    markdown = markdown.replace(
      /!\[([^\]]*)\]\(([^)]+)\)/g,
      (match, alt, imagePath) => {
        const trimmedPath = imagePath.trim()
        const baseUrl = window.location.origin

        // If it's an OSS/object storage URL (https:// or http://), convert to local path
        if (
          trimmedPath.startsWith('http://') ||
          trimmedPath.startsWith('https://')
        ) {
          // OSS URL format: https://.../admin/articles/{article_id}/images/{filename}
          // Or: https://.../media/articles/{article_id}/{filename}
          // Extract article ID and filename
          let articleId = null
          let filename = null

          // Try pattern: /admin/articles/{article_id}/images/{filename}
          const adminMatch = trimmedPath.match(
            /\/admin\/articles\/([^\/]+)\/images\/([^\/]+)$/
          )
          if (adminMatch) {
            ;[, articleId, filename] = adminMatch
          } else {
            // Try pattern: /media/articles/{article_id}/{filename}
            const mediaMatch = trimmedPath.match(
              /\/media\/articles\/([^\/]+)\/([^\/]+)$/
            )
            if (mediaMatch) {
              ;[, articleId, filename] = mediaMatch
            } else {
              // Try to extract from any path that contains article ID pattern (UUID)
              const uuidPattern =
                /([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/
              const uuidMatch = trimmedPath.match(uuidPattern)
              if (uuidMatch) {
                articleId = uuidMatch[1]
                // Extract filename from URL
                const pathParts = trimmedPath.split('/')
                filename = pathParts[pathParts.length - 1]
              }
            }
          }

          if (articleId && filename) {
            const localUrl = `${baseUrl}/media/articles/${articleId}/${filename}`
            return `![${alt}](${localUrl})`
          }

          return match
        }

        // If starts with /media/articles, convert to full URL (local HTTP service)
        if (trimmedPath.startsWith('/media/articles')) {
          const fullUrl = `${baseUrl}${trimmedPath}`
          return `![${alt}](${fullUrl})`
        }

        // If relative path starting with /, convert to full URL
        if (trimmedPath.startsWith('/')) {
          const fullUrl = `${baseUrl}${trimmedPath}`
          return `![${alt}](${fullUrl})`
        }

        // For relative paths (no leading /), try to construct URL
        // This handles cases like "images/photo.jpg"
        if (trimmedPath && !trimmedPath.includes('://')) {
          const fullUrl = `${baseUrl}/${trimmedPath}`
          return `![${alt}](${fullUrl})`
        }

        // Return original if no conversion needed
        return match
      }
    )

    const html = marked.parse(markdown)

    // Also process img tags in the HTML output (in case marked already converted them)
    // Always convert to local HTTP service URLs
    const processedHtml = html.replace(
      /<img([^>]*)\ssrc=["']([^"']+)["']([^>]*)>/gi,
      (match, before, src, after) => {
        const trimmedSrc = src.trim()
        const baseUrl = window.location.origin

        // If it's an OSS/object storage URL, convert to local path
        if (
          trimmedSrc.startsWith('http://') ||
          trimmedSrc.startsWith('https://')
        ) {
          // OSS URL format: https://.../admin/articles/{article_id}/images/{filename}
          // Or: https://.../media/articles/{article_id}/{filename}
          let articleId = null
          let filename = null

          // Try pattern: /admin/articles/{article_id}/images/{filename}
          const adminMatch = trimmedSrc.match(
            /\/admin\/articles\/([^\/]+)\/images\/([^\/]+)$/
          )
          if (adminMatch) {
            ;[, articleId, filename] = adminMatch
          } else {
            // Try pattern: /media/articles/{article_id}/{filename}
            const mediaMatch = trimmedSrc.match(
              /\/media\/articles\/([^\/]+)\/([^\/]+)$/
            )
            if (mediaMatch) {
              ;[, articleId, filename] = mediaMatch
            } else {
              // Try to extract from any path that contains article ID pattern (UUID)
              const uuidPattern =
                /([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/
              const uuidMatch = trimmedSrc.match(uuidPattern)
              if (uuidMatch) {
                articleId = uuidMatch[1]
                // Extract filename from URL
                const pathParts = trimmedSrc.split('/')
                filename = pathParts[pathParts.length - 1]
              }
            }
          }

          if (articleId && filename) {
            const localUrl = `${baseUrl}/media/articles/${articleId}/${filename}`
            return `<img${before} src="${localUrl}"${after}>`
          }

          return match
        }

        // Convert relative paths to full URLs (local HTTP service)
        if (trimmedSrc.startsWith('/')) {
          const fullUrl = `${baseUrl}${trimmedSrc}`
          return `<img${before} src="${fullUrl}"${after}>`
        }

        return match
      }
    )

    return sanitizeHtml(processedHtml)
  } catch (error) {
    return `<pre class="text-gray-600">${escapeHtml(props.content || '')}</pre>`
  }
})
</script>

<style scoped>
.markdown-content {
  @apply text-gray-700;
}

/* Override prose styles for better readability */
.markdown-content :deep(h1) {
  @apply text-xl font-bold text-gray-900 mt-6 mb-4 first:mt-0;
}

.markdown-content :deep(h2) {
  @apply text-lg font-semibold text-gray-900 mt-5 mb-3 first:mt-0;
}

.markdown-content :deep(h3) {
  @apply text-base font-medium text-gray-900 mt-4 mb-2 first:mt-0;
}

.markdown-content :deep(h4) {
  @apply text-sm font-medium text-gray-900 mt-3 mb-2 first:mt-0;
}

.markdown-content :deep(p) {
  @apply mb-3 leading-relaxed;
  white-space: pre-wrap;
}

.markdown-content :deep(br) {
  display: block;
  content: '';
  margin-bottom: 0.25em;
}

.markdown-content :deep(ul) {
  @apply list-disc list-outside mb-3 space-y-1 ml-6;
}

.markdown-content :deep(ol) {
  @apply list-decimal list-outside mb-3 space-y-1 ml-6;
}

.markdown-content :deep(li) {
  @apply text-gray-700;
}

.markdown-content :deep(blockquote) {
  @apply border-l-4 border-gray-300 pl-4 italic text-gray-600 my-4;
}

.markdown-content :deep(code) {
  @apply bg-gray-100 text-gray-800 px-1 py-0.5 rounded text-sm font-mono;
}

.markdown-content :deep(pre) {
  @apply bg-gray-900 border border-gray-700 p-4 rounded-lg my-4 text-sm overflow-x-auto;
  white-space: pre-wrap;
  word-wrap: break-word;
  word-break: break-all;
}

.markdown-content :deep(pre code) {
  @apply bg-transparent p-0 text-gray-100;
  white-space: pre-wrap;
  word-wrap: break-word;
  word-break: break-all;
}

/* Custom styles for code highlighting - terminal theme */
.markdown-content :deep(.hljs) {
  @apply bg-gray-900;
}

.markdown-content :deep(table) {
  @apply w-full border-collapse border border-gray-300 my-4;
}

.markdown-content :deep(th) {
  @apply bg-gray-50 border border-gray-300 px-3 py-2 text-left font-medium text-gray-900;
}

.markdown-content :deep(td) {
  @apply border border-gray-300 px-3 py-2 text-gray-700;
}

.markdown-content :deep(a) {
  @apply text-primary-600 hover:text-primary-700 underline;
}

.markdown-content :deep(img) {
  @apply max-w-full h-auto rounded-lg shadow-md my-4;
}

.markdown-content :deep(strong) {
  @apply font-semibold text-gray-900;
}

.markdown-content :deep(em) {
  @apply italic;
}

.markdown-content :deep(hr) {
  @apply border-t border-gray-300 my-6;
}
</style>
