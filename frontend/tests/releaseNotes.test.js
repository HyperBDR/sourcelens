import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  hasReleaseNotesForAudience,
  hasUnreadReleaseNotes,
  markReleaseNotesViewed,
  selectLocalizedReleaseNotes
} from '../src/utils/releaseNotes.js'

const manifest = {
  version: '1.2.0',
  releaseDate: '2026/08/03',
  categories: {
    feature: [
      {
        audience: 'user',
        en: 'Added release notes.',
        es: 'Se añadieron notas de la versión.',
        'zh-CN': '\u65b0\u589e\u66f4\u65b0\u65e5\u5fd7\u3002'
      },
      {
        audience: 'admin',
        en: 'Added an administrator control.',
        'zh-CN': '\u65b0\u589e\u7ba1\u7406\u5458\u63a7\u5236\u9879\u3002'
      }
    ],
    improvement: [
      {
        audience: 'user',
        en: 'Improved fallback behavior.'
      }
    ],
    fix: []
  }
}

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial))
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null
    },
    setItem(key, value) {
      values.set(key, String(value))
    }
  }
}

test('selects the current locale with an English per-entry fallback', () => {
  const groups = selectLocalizedReleaseNotes(manifest, 'zh-CN')

  assert.deepEqual(groups, [
    {
      type: 'feature',
      entries: [
        {
          audience: 'user',
          text: '\u65b0\u589e\u66f4\u65b0\u65e5\u5fd7\u3002'
        }
      ]
    },
    {
      type: 'improvement',
      entries: [
        {
          audience: 'user',
          text: 'Improved fallback behavior.'
        }
      ]
    }
  ])
})

test('falls back to English for unsupported locales', () => {
  const groups = selectLocalizedReleaseNotes(manifest, 'fr')

  assert.equal(groups[0].entries[0].text, 'Added release notes.')
})

test('selects Spanish release notes when available', () => {
  const groups = selectLocalizedReleaseNotes(manifest, 'es')

  assert.equal(groups[0].entries[0].text, 'Se añadieron notas de la versión.')
})

test('includes administrator entries only for administrators', () => {
  const userGroups = selectLocalizedReleaseNotes(manifest, 'en')
  const adminGroups = selectLocalizedReleaseNotes(manifest, 'en', true)

  assert.deepEqual(userGroups[0].entries, [
    { audience: 'user', text: 'Added release notes.' }
  ])
  assert.deepEqual(adminGroups[0].entries, [
    { audience: 'user', text: 'Added release notes.' },
    { audience: 'admin', text: 'Added an administrator control.' }
  ])
})

test('reports whether the current audience has visible release notes', () => {
  const adminOnlyManifest = {
    categories: {
      feature: [{ audience: 'admin', en: 'Admin only.' }]
    }
  }

  assert.equal(hasReleaseNotesForAudience(adminOnlyManifest), false)
  assert.equal(hasReleaseNotesForAudience(adminOnlyManifest, true), true)
})

test('marks viewed versions independently for users and administrators', () => {
  const storage = memoryStorage()

  assert.equal(hasUnreadReleaseNotes('1.2.0', storage), true)
  markReleaseNotesViewed('1.2.0', storage)
  assert.equal(hasUnreadReleaseNotes('1.2.0', storage), false)
  assert.equal(hasUnreadReleaseNotes('1.1.0', storage), true)
  assert.equal(hasUnreadReleaseNotes('1.2.0', storage, true), true)
  markReleaseNotesViewed('1.2.0', storage, true)
  assert.equal(hasUnreadReleaseNotes('1.2.0', storage, true), false)
})

test('does not show an unread indicator for local development builds', () => {
  assert.equal(hasUnreadReleaseNotes('dev', memoryStorage()), false)
  assert.equal(hasUnreadReleaseNotes('', memoryStorage()), false)
})

test('settings integrates the release-note view and unread indicator', async () => {
  const source = (path) =>
    readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')
  const [modal, releaseNotesSettings, dock, store] = await Promise.all([
    source('components/settings/UserSettingsModal.vue'),
    source('components/settings/ReleaseNotesSettings.vue'),
    source('components/lens/UserDock.vue'),
    source('store/ui.js')
  ])

  assert.match(modal, /ReleaseNotesSettings/)
  assert.match(modal, /activeSection === 'release-notes'/)
  assert.match(modal, /markReleaseNotesViewed/)
  assert.match(releaseNotesSettings, /userHasFeature\('admin_console'\)/)
  assert.match(releaseNotesSettings, /isAdmin\.value/)
  assert.match(releaseNotesSettings, /settings\.releaseNotes\.adminOnly/)
  assert.match(dock, /hasUnreadReleaseNotes/)
  assert.match(store, /release-notes\.json/)
  assert.match(store, /getReleaseNotesStorageKey/)
})
