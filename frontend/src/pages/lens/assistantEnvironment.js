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

export function buildMcpEnvironmentBinding(
  mcp,
  selectedEnvironmentSetUuid,
  draft = {}
) {
  return buildEnvironmentBinding(
    'mcp_uuid',
    mcp.uuid,
    mcp.environment,
    selectedEnvironmentSetUuid,
    draft
  )
}

export function mcpRequiredEnvironmentNames(mcp) {
  const references = new Set(mcp?.environment_references || [])
  environmentReferences({
    endpoint: mcp?.endpoint,
    config: mcp?.config
  }).forEach((name) => references.add(name))
  return (mcp?.environment || [])
    .filter((item) => item.required || references.has(item.name))
    .map((item) => item.name)
}

export function scopeEnvironmentSetValues(values, declaredNames) {
  if (!Array.isArray(declaredNames)) {
    return { values: values || [], unusedCount: 0 }
  }
  const declared = new Set(declaredNames)
  const scopedValues = (values || []).filter((item) => declared.has(item.key))
  return {
    values: scopedValues,
    unusedCount: (values || []).length - scopedValues.length
  }
}

export function environmentConfigurationComplete({
  selectedUuid,
  requiredNames,
  draftValues,
  savedKeys
}) {
  const enteredValues = draftValues || {}
  const required = requiredNames || []
  const hasEnteredValue = Object.values(enteredValues).some((value) =>
    String(value ?? '').trim()
  )
  if (!selectedUuid && required.length && !hasEnteredValue) return false

  const saved = new Set(savedKeys || [])
  return required.every(
    (name) => String(enteredValues[name] ?? '').trim() || saved.has(name)
  )
}

function environmentReferences(value) {
  if (Array.isArray(value)) {
    return value.reduce((references, item) => {
      environmentReferences(item).forEach((name) => references.add(name))
      return references
    }, new Set())
  }
  if (value && typeof value === 'object') {
    return environmentReferences(Object.values(value))
  }
  if (typeof value !== 'string') return new Set()
  return new Set(
    Array.from(value.matchAll(/\$\{([A-Z_][A-Z0-9_]*)\}/g), (match) => match[1])
  )
}

function buildEnvironmentBinding(
  resourceKey,
  resourceUuid,
  declarations,
  selectedEnvironmentSetUuid,
  draft
) {
  const selectedUuid =
    selectedEnvironmentSetUuid === '__new__'
      ? null
      : selectedEnvironmentSetUuid || null
  const binding = {
    [resourceKey]: resourceUuid,
    environment_variable_set_uuid: selectedUuid
  }
  const declaredNames = new Set((declarations || []).map((item) => item.name))
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
