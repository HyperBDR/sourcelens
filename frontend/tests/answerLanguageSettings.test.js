import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (path) =>
  readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('one language setting controls both UI and AI output', async () => {
  const [component, switcher, userStore, languages] = await Promise.all([
    source('components/settings/UserSettingsModal.vue'),
    source('components/ui/LanguageSwitcher.vue'),
    source('store/user.js'),
    source('utils/languages.js')
  ])

  assert.match(component, /id="ui-language"/)
  assert.doesNotMatch(component, /id="answer-language"/)
  assert.doesNotMatch(component, /getAnswerLanguageOptions/)
  assert.match(component, /userStore\.updateLanguage\(language\)/)
  assert.match(switcher, /userStore\.updateLanguage\(language\)/)
  assert.match(userStore, /profile_language: language/)
  assert.match(userStore, /preferencesStore\.setLanguage/)
  assert.doesNotMatch(languages, /ANSWER_LANGUAGES/)
})
