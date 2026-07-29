function bindingItem(binding, name, fallback) {
  if (!binding || typeof binding !== 'object') return null
  const resolvedName = name || fallback
  if (!resolvedName) return null
  return {
    name: resolvedName,
    enabled: binding.enabled !== false
  }
}

/** Normalize assistant list data for the read-only detail drawer. */
export function buildAssistantDetail(assistant = {}) {
  const workspaceDirectories = (assistant.selected_dirs || [])
    .map((directory) =>
      typeof directory === 'string' ? directory : directory?.path
    )
    .filter(Boolean)

  const skills = (assistant.skill_bindings || [])
    .map((binding) =>
      bindingItem(
        binding,
        binding?.skill_name || binding?.skill?.name,
        binding?.skill_uuid
      )
    )
    .filter(Boolean)

  const mcps = (assistant.mcp_bindings || [])
    .map((binding) =>
      bindingItem(
        binding,
        binding?.mcp_name || binding?.mcp_server?.name || binding?.mcp?.name,
        binding?.mcp_uuid
      )
    )
    .filter(Boolean)

  const grants = assistant.access_grants || []
  const authorizedUsers = grants
    .filter((grant) => grant?.type === 'user')
    .map((grant) => ({
      id: grant.id,
      username: grant.username || grant.name || '',
      email: grant.email || ''
    }))
  const authorizedGroups = grants
    .filter((grant) => grant?.type === 'group')
    .map((grant) => ({
      id: grant.id,
      name: grant.name || ''
    }))

  return {
    workspaceDirectories,
    skills,
    mcps,
    authorizedUsers,
    authorizedGroups
  }
}
