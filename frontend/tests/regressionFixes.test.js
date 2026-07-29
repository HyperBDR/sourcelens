import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (path) =>
  readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('active chat run exposes a localized stop action', async () => {
  const [chat, english, chinese] = await Promise.all([
    source('pages/lens/Chat.vue'),
    source('locales/en.json').then(JSON.parse),
    source('locales/zh-CN.json').then(JSON.parse)
  ])

  assert.match(chat, /isRunActive \? t\('common\.stop'\)/)
  assert.equal(english.common.stop, 'Stop')
  assert.equal(chinese.common.stop, '停止')
})

test('task statistics request all users unless a user is selected', async () => {
  const stats = await source('admin/pages/TaskManagement/Stats.vue')
  const fetchStart = stats.indexOf('async function fetchStats')
  const fetchEnd = stats.indexOf(
    'const res = await taskManagementApi.getStats(params)',
    fetchStart
  )
  const requestSetup = stats.slice(fetchStart, fetchEnd)

  assert.match(requestSetup, /my_tasks: 'false'/)
  assert.match(requestSetup, /params\.created_by = userScope\.value/)
})

test('drawer leave transition completes when animations are suspended', async () => {
  const drawer = await source('components/ui/BaseDrawer.vue')
  const { runDrawerTransition } =
    await import('../src/components/ui/drawerTransition.js')

  let cancelledAnimations = 0
  const suspendedAnimation = () => ({
    cancel() {
      cancelledAnimations += 1
    },
    finished: new Promise(() => {})
  })
  const panel = { animate: suspendedAnimation }
  const element = {
    animate: suspendedAnimation,
    querySelector() {
      return panel
    }
  }

  await new Promise((resolve, reject) => {
    const timeout = setTimeout(
      () => reject(new Error('drawer transition did not complete')),
      500
    )

    runDrawerTransition(element, 'leave', 10, () => {
      clearTimeout(timeout)
      resolve()
    })
  })

  assert.match(drawer, /<Transition\s+:css="false"/)
  assert.equal(cancelledAnimations, 2)
})

test('drawer skips visual transitions in a hidden document', async () => {
  const { runDrawerTransition } =
    await import('../src/components/ui/drawerTransition.js')
  let animationCount = 0
  let completed = false
  const panel = {
    animate() {
      animationCount += 1
    }
  }
  const element = {
    ownerDocument: { hidden: true },
    animate() {
      animationCount += 1
    },
    querySelector() {
      return panel
    }
  }

  runDrawerTransition(element, 'enter', 300, () => {
    completed = true
  })

  assert.equal(completed, true)
  assert.equal(animationCount, 0)
})
