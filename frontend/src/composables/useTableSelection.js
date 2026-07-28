import { computed, ref, watch } from 'vue'

export function useTableSelection(items, getKey = (item) => item.id) {
  const selectedIds = ref(new Set())

  const selectedRows = computed(() =>
    items.value.filter((item) => selectedIds.value.has(getKey(item)))
  )
  const allSelected = computed(
    () =>
      items.value.length > 0 && selectedRows.value.length === items.value.length
  )
  const someSelected = computed(
    () => selectedRows.value.length > 0 && !allSelected.value
  )

  function clearSelection() {
    selectedIds.value = new Set()
  }

  function setRowSelected(item, selected) {
    const next = new Set(selectedIds.value)
    const key = getKey(item)
    if (selected) next.add(key)
    else next.delete(key)
    selectedIds.value = next
  }

  function setAllSelected(selected) {
    selectedIds.value = selected
      ? new Set(items.value.map((item) => getKey(item)))
      : new Set()
  }

  watch(items, clearSelection)

  return {
    allSelected,
    clearSelection,
    selectedIds,
    selectedRows,
    setAllSelected,
    setRowSelected,
    someSelected
  }
}
