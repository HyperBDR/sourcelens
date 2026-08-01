import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (path) =>
  readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('password login submits an email credential', async () => {
  const [component, baseInput] = await Promise.all([
    source('components/auth/LoginForm.vue'),
    source('components/ui/BaseInput.vue')
  ])

  assert.match(component, /v-model="formData\.email"/)
  assert.match(component, /type="email"/)
  assert.match(component, /name="email"/)
  assert.match(component, /autocomplete="email"/)
  assert.match(component, /email: formData\.email/)
  assert.doesNotMatch(component, /username: formData\.username/)
  assert.match(baseInput, /:name="name"/)
  assert.match(baseInput, /name:\s*\{\s*type: String/)
})

test('password login messages identify email in both locales', async () => {
  const [english, chinese] = await Promise.all([
    source('locales/en.json'),
    source('locales/zh-CN.json')
  ])
  const en = JSON.parse(english)
  const zh = JSON.parse(chinese)

  assert.equal(
    en.auth.loginError,
    'Incorrect email or password, please try again'
  )
  assert.equal(zh.auth.loginError, '邮箱或密码错误，请重试')
  assert.match(en.auth.loginFailedMessage, /email and password/)
  assert.match(zh.auth.loginFailedMessage, /邮箱和密码/)
})

test('email code verification submits the detected UI language', async () => {
  const component = await source('components/auth/EmailCodeLogin.vue')

  assert.match(
    component,
    /loginWithCode\(\{[\s\S]*language: locale\.value[\s\S]*\}\)/
  )
})
