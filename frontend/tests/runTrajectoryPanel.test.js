import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = () =>
  readFile(
    new URL('../src/admin/pages/lens/RunTrajectoryPanel.vue', import.meta.url),
    'utf8'
  )

const jsonTreeSource = () =>
  readFile(
    new URL('../src/components/ui/JsonTree.vue', import.meta.url),
    'utf8'
  )

const jsonTreeNodeSource = () =>
  readFile(
    new URL('../src/components/ui/JsonTreeNode.vue', import.meta.url),
    'utf8'
  )

test('switching trajectory steps preserves the active inspector tab', async () => {
  const contents = await source()
  const selectEvent = contents.match(
    /function selectEvent\(event\) \{(?<body>[\s\S]*?)\n\}/
  )
  const inspectorTabs = contents.match(
    /const inspectorTabs = computed\(\(\) => (?<body>\[[\s\S]*?\])\)/
  )

  assert.ok(selectEvent?.groups?.body)
  assert.match(selectEvent.groups.body, /selectedEvent\.value = event/)
  assert.doesNotMatch(selectEvent.groups.body, /inspectorTab\.value/)
  assert.ok(inspectorTabs?.groups?.body)
  assert.match(inspectorTabs.groups.body, /id: 'summary'/)
  assert.match(inspectorTabs.groups.body, /id: 'payload'/)
  assert.match(inspectorTabs.groups.body, /id: 'raw'/)
  assert.doesNotMatch(inspectorTabs.groups.body, /selectedEvent/)
})

test('trajectory inspector exposes an accessible drag separator', async () => {
  const contents = await source()

  assert.match(contents, /class="trajectory-resize-handle"/)
  assert.match(contents, /role="separator"/)
  assert.match(contents, /aria-orientation="vertical"/)
  assert.match(contents, /@pointerdown="startInspectorResize"/)
  assert.match(contents, /@pointermove="resizeInspector"/)
  assert.match(contents, /@keydown="resizeInspectorWithKeyboard"/)
  assert.match(contents, /--trajectory-inspector-width/)
})

test('trajectory rows expose bounded depth indentation styles', async () => {
  const contents = await source()

  assert.match(contents, /:style="rowIndentStyle\(row\)"/)
  assert.match(contents, /function rowIndentStyle\(row\)/)
  assert.match(contents, /--trajectory-indent/)
  assert.match(contents, /padding-left: calc\(34px \+ var\(--trajectory-indent/)
  assert.match(contents, /padding-left: calc\(8px \+ var\(--trajectory-indent/)
})

test('trajectory summary exposes tool input and output previews', async () => {
  const contents = await source()

  assert.match(contents, /输入 \/ 输出/)
  assert.match(contents, /inspectorInput\(selectedEvent\)/)
  assert.match(contents, /inspectorOutput\(selectedEvent\)/)
  assert.match(contents, /function inspectorValue\(value\)/)
})

test('trajectory JSON uses compact recursive indentation', async () => {
  const [panel, tree, node] = await Promise.all([
    source(),
    jsonTreeSource(),
    jsonTreeNodeSource()
  ])

  assert.match(panel, /<JsonTree[\s\S]*?:indent="8"/)
  assert.match(tree, /indent: \{ type: Number, default: 14 \}/)
  assert.match(tree, /:indent="indent"/)
  assert.match(node, /depth \* indent/)
  assert.match(node, /:indent="indent"/)
})

test('active runs refresh trajectory events incrementally', async () => {
  const contents = await source()

  assert.match(contents, /runStatus: \{ type: String, default: '' \}/)
  assert.match(contents, /const ACTIVE_RUN_STATUSES = new Set/)
  assert.match(contents, /function scheduleRefresh\(\)/)
  assert.match(
    contents,
    /refreshTimer = setTimeout\(\(\) => fetchTrajectory\(true\), 2000\)/
  )
  assert.match(contents, /clearTimeout\(refreshTimer\)/)
})
