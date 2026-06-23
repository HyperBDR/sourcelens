import api from '@/api'

function unwrapResponse(response) {
  return response?.data?.data ?? response?.data ?? null
}

function unwrapList(payload) {
  if (Array.isArray(payload)) {
    return payload
  }
  if (Array.isArray(payload?.results)) {
    return payload.results
  }
  return []
}

export async function listAssistants() {
  const response = await api.get('/lens/assistants/')
  return unwrapList(unwrapResponse(response))
}

export async function getPublicAssistant(slug) {
  const response = await api.get(`/lens/public/assistants/${slug}/`)
  return unwrapResponse(response)
}

export async function getAssistant(uuid) {
  const response = await api.get(`/lens/assistants/${uuid}/`)
  return unwrapResponse(response)
}

export async function createAssistant(payload) {
  const response = await api.post('/lens/assistants/', payload)
  return unwrapResponse(response)
}

export async function updateAssistant(uuid, payload) {
  const response = await api.patch(`/lens/assistants/${uuid}/`, payload)
  return unwrapResponse(response)
}

export async function deleteAssistant(uuid) {
  const response = await api.delete(`/lens/assistants/${uuid}/`)
  return unwrapResponse(response)
}

export async function listLensNodes() {
  const response = await api.get('/lens/admin/lensnodes/')
  return unwrapList(unwrapResponse(response))
}

export async function getAdminRuns(params = {}) {
  const response = await api.get('/lens/admin/runs/', { params })
  return unwrapResponse(response)
}

export async function getAdminRun(uuid) {
  const response = await api.get(`/lens/admin/runs/${uuid}/`)
  return unwrapResponse(response)
}

export async function createLensNode(payload) {
  const response = await api.post('/lens/admin/lensnodes/', payload)
  return unwrapResponse(response)
}

export async function updateLensNode(uuid, payload) {
  const response = await api.patch(`/lens/admin/lensnodes/${uuid}/`, payload)
  return unwrapResponse(response)
}

export async function deleteLensNode(uuid) {
  const response = await api.delete(`/lens/admin/lensnodes/${uuid}/`)
  return unwrapResponse(response)
}

export async function scanLensNodeDirs(uuid, paths) {
  const response = await api.post(`/lens/admin/lensnodes/${uuid}/list-dirs/`, {
    paths
  })
  return unwrapResponse(response)
}

export async function checkLensNodeDataSourcePath(uuid, payload) {
  const response = await api.post(
    `/lens/admin/lensnodes/${uuid}/check-datasource-path/`,
    payload
  )
  return unwrapResponse(response)
}

export async function testLensNodeDataSourceConnection(uuid, payload) {
  const response = await api.post(
    `/lens/admin/lensnodes/${uuid}/test-datasource-connection/`,
    payload
  )
  return unwrapResponse(response)
}

export async function approveLensNode(uuid) {
  const response = await api.post(`/lens/admin/lensnodes/${uuid}/approve/`)
  return unwrapResponse(response)
}

export async function rejectLensNode(uuid) {
  const response = await api.post(`/lens/admin/lensnodes/${uuid}/reject/`)
  return unwrapResponse(response)
}

export async function issueLensNodeToken(uuid) {
  const response = await api.post(`/lens/admin/lensnodes/${uuid}/issue-token/`)
  return unwrapResponse(response)
}

export async function revokeLensNodeToken(uuid) {
  const response = await api.post(`/lens/admin/lensnodes/${uuid}/revoke-token/`)
  return unwrapResponse(response)
}

export async function listSessions(assistantSlug = '') {
  const params = assistantSlug ? { assistant_slug: assistantSlug } : {}
  const response = await api.get('/lens/sessions/', { params })
  return unwrapList(unwrapResponse(response))
}

export async function getSession(uuid) {
  const response = await api.get(`/lens/sessions/${uuid}/`)
  return unwrapResponse(response)
}

export async function listMessages(sessionUuid) {
  const response = await api.get(`/lens/sessions/${sessionUuid}/messages/`)
  return unwrapList(unwrapResponse(response))
}

export async function createSession(payload) {
  const response = await api.post('/lens/sessions/', payload)
  return unwrapResponse(response)
}

export async function updateSession(uuid, payload) {
  const response = await api.patch(`/lens/sessions/${uuid}/`, payload)
  return unwrapResponse(response)
}

export async function deleteSession(uuid) {
  await api.delete(`/lens/sessions/${uuid}/`)
}

export async function createRun(sessionUuid, payload) {
  const response = await api.post(
    `/lens/sessions/${sessionUuid}/runs/`,
    payload
  )
  return unwrapResponse(response)
}

export async function getRun(uuid) {
  const response = await api.get(`/lens/runs/${uuid}/`)
  return unwrapResponse(response)
}

export async function cancelRun(runUuid) {
  const response = await api.post(`/lens/runs/${runUuid}/cancel/`)
  return unwrapResponse(response)
}

export async function listDataSources() {
  const response = await api.get('/lens/admin/datasources/')
  return unwrapList(unwrapResponse(response))
}

export async function createDataSource(payload) {
  const response = await api.post('/lens/admin/datasources/', payload)
  return unwrapResponse(response)
}

export async function updateDataSource(uuid, payload) {
  const response = await api.patch(`/lens/admin/datasources/${uuid}/`, payload)
  return unwrapResponse(response)
}

export async function deleteDataSource(uuid) {
  const response = await api.delete(`/lens/admin/datasources/${uuid}/`)
  return unwrapResponse(response)
}

export async function listCredentials(params = {}) {
  const response = await api.get('/lens/admin/credentials/', { params })
  return unwrapList(unwrapResponse(response))
}

export async function createCredential(payload) {
  const response = await api.post('/lens/admin/credentials/', payload)
  return unwrapResponse(response)
}

export async function updateCredential(uuid, payload) {
  const response = await api.patch(`/lens/admin/credentials/${uuid}/`, payload)
  return unwrapResponse(response)
}

export async function revealCredential(uuid) {
  const response = await api.post(`/lens/admin/credentials/${uuid}/reveal/`)
  return unwrapResponse(response)
}

export async function deleteCredential(uuid) {
  const response = await api.delete(`/lens/admin/credentials/${uuid}/`)
  return unwrapResponse(response)
}

export async function syncDataSource(uuid, payload = {}) {
  const response = await api.post(
    `/lens/admin/datasources/${uuid}/sync/`,
    payload
  )
  return unwrapResponse(response)
}

export async function setDataSourceEnabled(uuid, enabled) {
  const response = await api.post(
    `/lens/admin/datasources/${uuid}/set-enabled/`,
    { enabled }
  )
  return unwrapResponse(response)
}

export async function cancelDataSourceSync(uuid) {
  const response = await api.post(`/lens/admin/datasources/${uuid}/cancel-sync/`)
  return unwrapResponse(response)
}

export async function listSkills() {
  const response = await api.get('/lens/admin/skills/')
  return unwrapList(unwrapResponse(response))
}

export async function createSkill(payload) {
  const response = await api.post('/lens/admin/skills/', payload)
  return unwrapResponse(response)
}

export async function updateSkill(uuid, payload) {
  const response = await api.patch(`/lens/admin/skills/${uuid}/`, payload)
  return unwrapResponse(response)
}

export async function deleteSkill(uuid) {
  const response = await api.delete(`/lens/admin/skills/${uuid}/`)
  return unwrapResponse(response)
}

export async function beautifySkill(payload) {
  const response = await api.post('/lens/admin/skills/beautify/', payload)
  return unwrapResponse(response)
}

export async function listMcpServers() {
  const response = await api.get('/lens/admin/mcp-servers/')
  return unwrapList(unwrapResponse(response))
}

export async function createMcpServer(payload) {
  const response = await api.post('/lens/admin/mcp-servers/', payload)
  return unwrapResponse(response)
}

export async function updateMcpServer(uuid, payload) {
  const response = await api.patch(`/lens/admin/mcp-servers/${uuid}/`, payload)
  return unwrapResponse(response)
}

export async function deleteMcpServer(uuid) {
  const response = await api.delete(`/lens/admin/mcp-servers/${uuid}/`)
  return unwrapResponse(response)
}

export async function listGlobalSettings() {
  const response = await api.get('/lens/admin/global-settings/')
  return unwrapList(unwrapResponse(response))
}

export async function createGlobalSetting(payload) {
  const response = await api.post('/lens/admin/global-settings/', payload)
  return unwrapResponse(response)
}

export async function updateGlobalSetting(key, payload) {
  const response = await api.patch(
    `/lens/admin/global-settings/${encodeURIComponent(key)}/`,
    payload
  )
  return unwrapResponse(response)
}

export async function getSystemHealth() {
  const response = await api.get('/lens/admin/global-settings/system-health/')
  return unwrapList(unwrapResponse(response))
}

export async function updateSystemTaskEnabled(taskType, enabled) {
  const response = await api.patch(
    '/lens/admin/global-settings/system-health/',
    {
      task_type: taskType,
      enabled
    }
  )
  return unwrapResponse(response)
}

// Public shareable Q&A

export async function shareRun(runUuid, payload = {}) {
  const response = await api.post(`/lens/runs/${runUuid}/share/`, payload)
  return unwrapResponse(response)
}

export async function listMyShares() {
  const response = await api.get('/lens/shares/')
  return unwrapList(unwrapResponse(response))
}

export async function updateMyShare(uuid, payload) {
  const response = await api.patch(`/lens/shares/${uuid}/`, payload)
  return unwrapResponse(response)
}

export async function deleteShare(uuid) {
  await api.delete(`/lens/shares/${uuid}/`)
}

export async function getPublicQa(token) {
  const response = await api.get(`/lens/public/qa/${token}/`)
  return unwrapResponse(response)
}

export async function getPublicAssistantQa(slug, params = {}) {
  const response = await api.get(`/lens/public/assistants/${slug}/qa/`, {
    params
  })
  return unwrapResponse(response)
}

export async function listAdminShares(params = {}) {
  const response = await api.get('/lens/admin/shares/', { params })
  return unwrapResponse(response)
}

export async function updateAdminShare(uuid, payload) {
  const response = await api.patch(`/lens/admin/shares/${uuid}/`, payload)
  return unwrapResponse(response)
}
