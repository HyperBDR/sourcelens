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
    if (
      typeof skill.slug === 'string' &&
      skill.slug.endsWith('-workspace-guide')
    ) {
      return false
    }
    if (!query) return true

    return [skill.name, skill.slug, skillDescription(skill)].some((value) =>
      String(value || '')
        .toLocaleLowerCase()
        .includes(query)
    )
  })
}
