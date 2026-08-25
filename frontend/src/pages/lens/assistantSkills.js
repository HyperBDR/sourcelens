export function skillDescription(skill) {
  const definition = skill?.definition || {}
  return (
    skill?.description ||
    definition.description ||
    definition.summary ||
    skill?.package_manifest?.description ||
    ''
  )
}

export function filterSelectableSkills(skills, keyword) {
  const query = String(keyword || '')
    .trim()
    .toLocaleLowerCase()
  return (skills || []).filter((skill) => {
    if (skill.kind === 'workspace_guide') {
      return false
    }
    if (!query) return true

    return [skill.name, skill.package_name, skillDescription(skill)].some(
      (value) =>
        String(value || '')
          .toLocaleLowerCase()
          .includes(query)
    )
  })
}

export function sortSkillsBySelection(skills, selectedUuids) {
  const selected = new Set(selectedUuids || [])
  return [...(skills || [])].sort(
    (left, right) =>
      Number(selected.has(right.uuid)) - Number(selected.has(left.uuid))
  )
}
