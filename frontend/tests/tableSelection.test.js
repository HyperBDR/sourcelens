import assert from 'node:assert/strict'
import test from 'node:test'

import { nextTick, ref } from 'vue'

import { useTableSelection } from '../src/composables/useTableSelection.js'

test('selects individual rows and all rows on the current page', () => {
  const rows = ref([{ id: 1 }, { id: 2 }])
  const selection = useTableSelection(rows)

  selection.setRowSelected(rows.value[0], true)
  assert.deepEqual(selection.selectedRows.value, [{ id: 1 }])
  assert.equal(selection.someSelected.value, true)
  assert.equal(selection.allSelected.value, false)

  selection.setAllSelected(true)
  assert.deepEqual(selection.selectedRows.value, rows.value)
  assert.equal(selection.allSelected.value, true)
  assert.equal(selection.someSelected.value, false)

  selection.setAllSelected(false)
  assert.equal(selection.selectedRows.value.length, 0)
})

test('clears selection when the visible page changes', async () => {
  const rows = ref([{ uuid: 'first' }, { uuid: 'second' }])
  const selection = useTableSelection(rows, (row) => row.uuid)

  selection.setAllSelected(true)
  rows.value = [{ uuid: 'third' }]
  await nextTick()

  assert.equal(selection.selectedRows.value.length, 0)
  assert.equal(selection.selectedIds.value.size, 0)
})
