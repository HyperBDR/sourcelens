import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { toDocumentLang } from '../src/utils/documentLang.js'

const readSource = (path) =>
  readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

const flattenKeys = (value, prefix = '', output = new Set()) => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) {
      const next = prefix ? `${prefix}.${key}` : key
      flattenKeys(child, next, output)
    }
    return output
  }

  output.add(prefix)
  return output
}

test('Spanish is registered as a supported UI language', () => {
  const i18n = readSource('i18n/index.js')
  const languages = readSource('utils/languages.js')
  const notificationChannels = readSource(
    'admin/pages/Notifications/Channels.vue'
  )

  assert.match(i18n, /SUPPORTED_UI_LANGUAGES = \['en', 'zh-CN', 'es'\]/)
  assert.match(i18n, /import es from '..\/locales\/es\.json'/)
  assert.match(i18n, /import adminEs from '..\/admin\/locales\/es\.json'/)
  assert.match(languages, /es: '🇪🇸'/)
  assert.match(notificationChannels, /<option value="es">/)
  assert.match(notificationChannels, /channels\.languageEs/)
})

test('Spanish locale files cover every English message key', () => {
  for (const directory of ['locales', 'admin/locales']) {
    const english = JSON.parse(readSource(`${directory}/en.json`))
    const spanish = JSON.parse(readSource(`${directory}/es.json`))
    const missing = [...flattenKeys(english)].filter(
      (key) => !flattenKeys(spanish).has(key)
    )

    assert.deepEqual(missing, [], `Missing Spanish keys in ${directory}`)
  }
})

test('core Spanish messages are translated from their English source', () => {
  const app = JSON.parse(readSource('locales/es.json'))

  assert.equal(app.common.save, 'Guardar')
  assert.equal(app.auth.loginTitle, 'Inicie sesión en SourceLens')
  assert.equal(app.settings.preferences.languages.es, 'Español')
})

test('Spanish maps to its BCP-47 document language', () => {
  assert.equal(toDocumentLang('es'), 'es')
})

test('Spanish translations preserve interpolation placeholders', () => {
  for (const directory of ['locales', 'admin/locales']) {
    const english = JSON.parse(readSource(`${directory}/en.json`))
    const spanish = JSON.parse(readSource(`${directory}/es.json`))
    const mismatches = []

    const compare = (source, translation, key = '') => {
      if (source && typeof source === 'object' && !Array.isArray(source)) {
        for (const childKey of Object.keys(source)) {
          compare(
            source[childKey],
            translation[childKey],
            key ? `${key}.${childKey}` : childKey
          )
        }
        return
      }

      if (typeof source !== 'string') return
      const sourcePlaceholders = source.match(/\{[^{}]+\}/g) || []
      const translatedPlaceholders = translation.match(/\{[^{}]+\}/g) || []
      if (
        sourcePlaceholders.sort().join() !==
        translatedPlaceholders.sort().join()
      ) {
        mismatches.push(key)
      }
    }

    compare(english, spanish)
    assert.deepEqual(mismatches, [], `Invalid placeholders in ${directory}`)
  }
})

test('Spanish translations preserve required whitespace around placeholders', () => {
  for (const directory of ['locales', 'admin/locales']) {
    const english = JSON.parse(readSource(`${directory}/en.json`))
    const spanish = JSON.parse(readSource(`${directory}/es.json`))
    const mismatches = []

    const compare = (source, translation, key = '') => {
      if (source && typeof source === 'object' && !Array.isArray(source)) {
        for (const childKey of Object.keys(source)) {
          compare(
            source[childKey],
            translation[childKey],
            key ? `${key}.${childKey}` : childKey
          )
        }
        return
      }

      if (typeof source !== 'string') return
      for (const placeholder of source.match(/\{[^{}]+\}/g) || []) {
        const sourceIndex = source.indexOf(placeholder)
        const translatedIndex = translation.indexOf(placeholder)
        if (translatedIndex < 0) continue

        const sourceHasSpaceBefore = /\s/.test(source[sourceIndex - 1] || '')
        const sourceHasSpaceAfter = /\s/.test(
          source[sourceIndex + placeholder.length] || ''
        )
        const translationHasSpaceBefore = /\s/.test(
          translation[translatedIndex - 1] || ''
        )
        const translationHasSpaceAfter = /\s/.test(
          translation[translatedIndex + placeholder.length] || ''
        )

        if (
          (sourceHasSpaceBefore && !translationHasSpaceBefore) ||
          (sourceHasSpaceAfter && !translationHasSpaceAfter)
        ) {
          mismatches.push(key)
        }
      }
    }

    compare(english, spanish)
    assert.deepEqual(
      [...new Set(mismatches)],
      [],
      `Invalid placeholder whitespace in ${directory}`
    )
  }
})

test('critical Spanish product copy is accurate and fully translated', () => {
  const app = JSON.parse(readSource('locales/es.json'))
  const admin = JSON.parse(readSource('admin/locales/es.json'))
  const packageGuide = admin.lensAdmin.skills.packageGuidePrompt

  assert.equal(app.lens.chat.deleteSession, 'Eliminar sesión')
  assert.match(app.lens.chat.deleteSessionConfirm, /no se puede deshacer/i)
  assert.equal(app.settings.modal.allAssistants, 'Todos los asistentes')
  assert.equal(admin.lensRuns.title, 'Centro de operaciones de ejecuciones')
  assert.equal(
    admin.lensAdmin.skills.boundAssistants,
    'Asistentes vinculados ({count})'
  )
  assert.match(packageGuide, /como máximo 50 MB/i)
  assert.match(packageGuide, /\^\[A-Z_\]\[A-Z0-9_\]\*\$/)
  assert.doesNotMatch(packageGuide, /al menos 50 MB/i)
  assert.doesNotMatch(JSON.stringify(app), /auxiliar|período de sesiones/i)
  assert.doesNotMatch(JSON.stringify(admin), /habilidad|cremallera/i)
})

test('long Spanish copy does not silently fall back to English', () => {
  for (const directory of ['locales', 'admin/locales']) {
    const english = JSON.parse(readSource(`${directory}/en.json`))
    const spanish = JSON.parse(readSource(`${directory}/es.json`))
    const untranslated = []

    const compare = (source, translation, key = '') => {
      if (source && typeof source === 'object' && !Array.isArray(source)) {
        for (const childKey of Object.keys(source)) {
          compare(
            source[childKey],
            translation[childKey],
            key ? `${key}.${childKey}` : childKey
          )
        }
        return
      }

      if (
        typeof source === 'string' &&
        source.length > 40 &&
        source === translation
      ) {
        untranslated.push(key)
      }
    }

    compare(english, spanish)
    assert.deepEqual(untranslated, [], `Untranslated copy in ${directory}`)
  }
})
