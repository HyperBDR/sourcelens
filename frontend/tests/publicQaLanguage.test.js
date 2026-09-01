import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const source = (path) =>
  readFileSync(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('public Q&A surfaces explain original-language content', () => {
  const detail = source('pages/lens/PublicQa.vue')
  const card = source('components/lens/SharedQaCard.vue')

  assert.match(detail, /contentLanguageNotice/)
  assert.match(detail, /originalLanguageNotice/)
  assert.match(detail, /content_language/)
  assert.match(card, /contentLanguageNotice/)
  assert.match(card, /content_language/)
})

test('all public Q&A locales contain language notices', () => {
  for (const locale of ['en', 'zh-CN', 'es']) {
    const messages = JSON.parse(source(`locales/${locale}.json`))

    assert.ok(messages.lens.qa.contentLanguageNotice)
    assert.ok(messages.lens.qa.originalLanguageNotice)
  }
})
