import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (path) =>
  readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('settings keep UI and AI answer languages independent', async () => {
  const [component, languages] = await Promise.all([
    source('components/settings/UserSettingsModal.vue'),
    source('utils/languages.js')
  ])

  assert.match(component, /id="ui-language"/)
  assert.match(component, /id="answer-language"/)
  assert.match(component, /profile_language: language/)
  assert.match(component, /userInfo\?\.profile\?\.language/)
  for (const language of ['en-US', 'zh-CN']) {
    assert.match(languages, new RegExp(`['"]${language}['"]`))
  }
  for (const language of ['es', 'ja-JP', 'ko-KR']) {
    assert.doesNotMatch(languages, new RegExp(`['"]${language}['"]`))
  }
})
