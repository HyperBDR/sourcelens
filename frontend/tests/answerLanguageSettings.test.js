import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (path) =>
  readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('one language setting controls both UI and AI output', async () => {
  const [component, switcher, userStore, preferencesStore, languages] =
    await Promise.all([
      source('components/settings/UserSettingsModal.vue'),
      source('components/ui/LanguageSwitcher.vue'),
      source('store/user.js'),
      source('store/preferences.js'),
      source('utils/languages.js')
    ])

  assert.match(component, /id="ui-language"/)
  assert.match(component, /@update:model-value="selectLanguage"/)
  assert.doesNotMatch(component, /@change="selectLanguage/)
  assert.doesNotMatch(component, /id="answer-language"/)
  assert.doesNotMatch(component, /getAnswerLanguageOptions/)
  assert.match(component, /userStore\.updateLanguage\(language\)/)
  assert.match(switcher, /userStore\.updateLanguage\(language\)/)
  assert.match(userStore, /profile_language: language/)
  assert.match(userStore, /preferencesStore\.setLanguage/)
  assert.match(
    preferencesStore,
    /i18n\.global\.locale\.value = normalizedLanguage/
  )
  assert.match(
    preferencesStore,
    /document\.documentElement\.lang = toDocumentLang\(normalizedLanguage\)/
  )
  assert.match(
    preferencesStore,
    /localStorage\.setItem\('userLanguage', normalizedLanguage\)/
  )
  assert.doesNotMatch(languages, /ANSWER_LANGUAGES/)
})

test('controlled credential selects consume value updates directly', async () => {
  const component = await source('pages/lens/DataSourceFormDrawer.vue')
  const valueBindings = component.match(/:model-value="form\.credential_uuid"/g)
  const updateBindings = component.match(
    /@update:model-value="handleCredentialChange"/g
  )

  assert.equal(valueBindings?.length, 2)
  assert.equal(updateBindings?.length, 2)
  assert.doesNotMatch(component, /@change="handleCredentialChange"/)
  assert.match(component, /handleCredentialChange\(nextUuid\)/)
  assert.doesNotMatch(component, /handleCredentialChange\(event\)/)
})
