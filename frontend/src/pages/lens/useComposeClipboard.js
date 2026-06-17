import { ref } from 'vue'

import { copyToClipboard } from '@/utils/clipboard'

/**
 * Copy / download actions for a generated docker-compose file.
 *
 * `getText` returns the current compose text. Optional `before` runs first and
 * must resolve truthy to proceed (e.g. create the node and issue a token on
 * demand, so copying always hands back a runnable compose).
 */
export function useComposeClipboard(getText, options = {}) {
  const { before, fileName = 'docker-compose.yml' } = options
  const copied = ref(false)

  async function copy() {
    if (before && !(await before())) return
    if (await copyToClipboard(getText())) {
      copied.value = true
      setTimeout(() => {
        copied.value = false
      }, 2000)
    }
  }

  async function download() {
    if (before && !(await before())) return
    const blob = new Blob([getText()], { type: 'text/yaml' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = fileName
    link.click()
    URL.revokeObjectURL(url)
  }

  return { copied, copy, download }
}
