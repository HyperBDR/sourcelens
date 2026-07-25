export function buildSkillEnvironmentBinding(
  skill,
  selectedEnvironmentSetUuid,
  draft = {}
) {
  const selectedUuid =
    selectedEnvironmentSetUuid === '__new__'
      ? null
      : selectedEnvironmentSetUuid || null
  const binding = {
    skill_uuid: skill.uuid,
    environment_variable_set_uuid: selectedUuid
  }
  const declaredNames = new Set(
    (skill.definition?.environment || []).map((item) => item.name)
  )
  const environmentValues = Object.entries(draft.values || {})
    .filter(
      ([name, value]) =>
        declaredNames.has(name) && String(value ?? '').trim().length > 0
    )
    .map(([key, value]) => ({ key, value }))

  if (selectedEnvironmentSetUuid === '__new__' && draft.name?.trim()) {
    binding.environment_variable_set_name = draft.name.trim()
  }
  if (environmentValues.length) {
    binding.environment_values = environmentValues
  }
  return binding
}
