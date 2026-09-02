import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (path) =>
  readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('Plugin data sources use installed manifests and Connections', async () => {
  const [page, drawer] = await Promise.all([
    source('pages/lens/DataSources.vue'),
    source('pages/lens/DataSourceFormDrawer.vue')
  ])

  assert.match(page, /listPlugins/)
  assert.match(page, /pluginManifests/)
  assert.match(page, /isPluginSourceType/)
  assert.match(page, /payload\.plugin_key = form\.value\.plugin_key/)
  assert.match(page, /payload\.connection_uuid = form\.value\.connection_uuid/)
  assert.match(page, /payload\.datasource_config = buildPluginDatasourceConfig/)
  assert.match(page, /payload\.credential_uuid = null/)
  assert.match(page, /getConnectionResources/)
  assert.match(drawer, /isPluginSourceType/)
  assert.match(drawer, /form\.connection_uuid/)
  assert.match(drawer, /pluginResources/)
  assert.doesNotMatch(page, /getPluginManifest\('github'\)/)
  assert.doesNotMatch(drawer, /form\.source_type === 'github'/)
  assert.doesNotMatch(drawer, /githubPluginRepositories/)
  assert.doesNotMatch(drawer, /github\.repositories/)
  assert.doesNotMatch(drawer, /github\.repository\.branches/)
})

test('Direct Assistants bind installed Plugin tools without provider branches', async () => {
  const [page, drawer] = await Promise.all([
    source('pages/lens/Assistants.vue'),
    source('pages/lens/AssistantFormDrawerDirectEnvironment.vue')
  ])

  assert.match(page, /plugin_bindings:/)
  assert.match(page, /form\.value\.plugin_bindings/)
  assert.match(page, /listPlugins/)
  assert.match(page, /pluginManifests/)
  assert.doesNotMatch(page, /plugin_bindings[\s\S]{0,300}secret/)
  assert.match(drawer, /pluginManifests/)
  assert.match(drawer, /form\.plugin_bindings/)
  assert.match(drawer, /togglePluginConnection/)
  assert.match(drawer, /missingSkillPluginRequirements/)
  assert.match(drawer, /hasGeneralChatExecutionTool/)
  assert.match(drawer, /pluginAllTools/)
  assert.doesNotMatch(drawer, /togglePluginTool/)
  assert.doesNotMatch(drawer, /pluginTools\(/)
  assert.doesNotMatch(page, /tools:\s*\[\.\.\.\(binding\.tools/)
  assert.doesNotMatch(drawer, /githubConnections/)
  assert.doesNotMatch(drawer, /githubPluginTools/)
  assert.doesNotMatch(drawer, /githubPluginManifest/)
})

test('General Chat treats Skills as optional when Plugin tools are enabled', async () => {
  const [drawer, chinese, english] = await Promise.all([
    source('pages/lens/AssistantFormDrawerDirectEnvironment.vue'),
    source('admin/locales/zh-CN.json'),
    source('admin/locales/en.json')
  ])

  assert.match(drawer, /t\('lensAdmin\.wizard\.skillsSection'\)/)
  assert.doesNotMatch(drawer, /skillsSectionRequired/)
  assert.match(drawer, /hasGeneralChatExecutionTool/)
  assert.doesNotMatch(chinese, /skillsSectionRequired/)
  assert.doesNotMatch(english, /skillsSectionRequired/)
  assert.match(chinese, /至少需要一个已启用的 Skill 或内置插件工具/)
  assert.match(english, /at least one enabled Skill or built-in Plugin tool/)
})

test('manifest resource options preserve an existing dependent value', async () => {
  const renderer = await source('components/lens/ManifestSchemaForm.vue')

  assert.match(renderer, /candidate\.depends_on/)
  assert.match(renderer, /resource-options-request/)
  assert.match(renderer, /isResourceOptionLoading/)
  assert.match(renderer, /fieldValue\(field\)/)
})

test('Connection management keeps Plugin secrets write-only in the form', async () => {
  const [page, renderer, api] = await Promise.all([
    source('pages/lens/Connections.vue'),
    source('components/lens/ManifestSchemaForm.vue'),
    source('api/lens.js')
  ])

  assert.match(renderer, /field\.format === 'password'/)
  assert.match(renderer, /new-password/)
  assert.match(page, /field\.format === 'password'/)
  assert.match(page, /!hasFieldValue\(value\)/)
  assert.doesNotMatch(page, /row\.secret_value/)
  assert.match(api, /connections\/\$\{uuid\}\/validate/)
  assert.match(api, /connections\/\$\{uuid\}\/resources/)
  assert.match(api, /connections\/\$\{uuid\}\/resource-candidates/)
  assert.match(api, /connections\/resource-preview/)
  assert.match(page, /previewConnectionResources/)
  assert.match(page, /getConnectionResourceCandidates/)
  assert.match(page, /discoverConnectionResources/)
  assert.match(page, /canDiscoverConnectionResources/)
  assert.match(page, /storedSecretPlaceholder/)
  assert.match(page, /row\.secret_hint/)
  assert.doesNotMatch(api, /connections\/\$\{uuid\}\/revoke/)
  assert.doesNotMatch(page, /revokeConnection/)
  assert.match(page, /row\.status === 'active'/)
  assert.doesNotMatch(page, /revokeConfirm/)
})

test('manifest schema renderer supports safe scalar, secret, array and resource fields', async () => {
  const renderer = await source('components/lens/ManifestSchemaForm.vue')

  assert.match(renderer, /provider-resource/)
  assert.match(renderer, /provider-resource-option/)
  assert.match(renderer, /resources/)
  assert.match(renderer, /depends_on/)
  assert.match(renderer, /field\.format === 'password'/)
  assert.match(renderer, /type="checkbox"/)
  assert.match(renderer, /update:modelValue/)
  assert.match(renderer, /properties/)
})

test('connection resource trees stay hidden until scope values exist', async () => {
  const renderer = await source('components/lens/ManifestSchemaForm.vue')

  assert.match(renderer, /shouldRenderTree\(field\)/)
  assert.match(renderer, /optionsFor\(field\)\.length > 0/)
  assert.match(renderer, /if \(isTreeField\(field\)\) return normalized/)
  assert.match(renderer, /emptyResourceText/)
  assert.match(renderer, /treeSearchQuery/)
  assert.match(renderer, /filteredTreeGroups/)
  assert.match(renderer, /toggleTreeGroup/)
  assert.match(renderer, /aria-expanded/)
  assert.match(renderer, /treeSearchPlaceholder/)
})

test('connection resource candidates are reset when the secret changes', async () => {
  const page = await source('pages/lens/Connections.vue')

  assert.match(page, /@update:model-value="updateConnectionForm"/)
  assert.match(page, /connectionResourceCandidates\.value = \[\]/)
  assert.match(page, /nextForm\[resourceKey\] = \[\]/)
})

test('connection forms pass a shared input style to manifest fields', async () => {
  const [page, renderer] = await Promise.all([
    source('pages/lens/Connections.vue'),
    source('components/lens/ManifestSchemaForm.vue')
  ])

  assert.match(page, /control-class="connection-form-input"/)
  assert.match(renderer, /controlClass/)
})

test('datasource wizard exposes completed steps for quick navigation', async () => {
  const drawer = await source('pages/lens/DataSourceFormDrawer.vue')

  assert.match(
    drawer,
    /aria-current="i \+ 1 === wizardStep \? 'step' : undefined"/
  )
  assert.match(drawer, /:disabled="i \+ 1 > wizardStep"/)
  assert.match(drawer, /goToWizardStep\(i \+ 1\)/)
})

test('datasource wizard groups creation into three steps', async () => {
  const drawer = await source('pages/lens/DataSourceFormDrawer.vue')

  assert.match(drawer, /key: 'basic'/)
  assert.match(drawer, /key: 'connection'/)
  assert.match(drawer, /key: 'sync'/)
  assert.match(drawer, /processingTitle/)
  assert.match(drawer, /conversionOpen/)
  assert.doesNotMatch(drawer, /key: 'conversion'/)
})

test('datasource target path check follows the semantic sync step', async () => {
  const drawer = await source('pages/lens/DataSourceFormDrawer.vue')

  assert.match(drawer, /activeStepKey\.value !== 'sync'/)
  assert.doesNotMatch(drawer, /wizardStep\.value !== 4/)
})

test('plugin datasource resource discovery does not require a LensNode', async () => {
  const page = await source('pages/lens/DataSources.vue')
  const pluginBranch = page.indexOf(
    'if (isPluginSourceType(form.value.source_type))'
  )
  const nodeGuard = page.indexOf('if (!form.value.lensnode_uuid) return')

  assert.ok(pluginBranch >= 0)
  assert.ok(nodeGuard >= 0)
  assert.ok(pluginBranch < nodeGuard)
})

test('plugin datasource resources load on the connection step', async () => {
  const drawer = await source('pages/lens/DataSourceFormDrawer.vue')

  assert.match(drawer, /activeStepKey\.value === 'connection'/)
  assert.match(drawer, /activeStepKey\.value === 'sync'/)
})

test('Connection management renders manifest connection fields instead of GitHub-only inputs', async () => {
  const page = await source('pages/lens/Connections.vue')

  assert.match(page, /ManifestSchemaForm/)
  assert.match(page, /manifest\.connection_schema/)
  assert.match(page, /listPlugins/)
  assert.match(page, /field\.write_to/)
  assert.doesNotMatch(page, /v-model="form\.repositories"/)
  assert.doesNotMatch(page, /<option value="github">/)
  assert.doesNotMatch(page, /plugin_key: 'github'/)
})

test('Plugin datasource fields use only the generic manifest resource contract', async () => {
  const [page, drawer, api] = await Promise.all([
    source('pages/lens/DataSources.vue'),
    source('pages/lens/DataSourceFormDrawer.vue'),
    source('api/lens.js')
  ])

  assert.match(drawer, /ManifestSchemaForm/)
  assert.match(drawer, /datasourceSchema/)
  assert.match(drawer, /pluginResources/)
  assert.match(drawer, /updatePluginConfig/)
  assert.match(drawer, /request-resource-options/)
  assert.match(page, /loadPluginResourceOptions/)
  assert.match(api, /getConnectionResources\(uuid, params = \{\}\)/)
  assert.doesNotMatch(drawer, /githubDatasourceSchema/)
  assert.doesNotMatch(drawer, /githubResourceOptions/)
  assert.doesNotMatch(drawer, /selectedPluginRepository/)
})

test('MCP Plugin adapters select dynamic Connections and manifest tools', async () => {
  const page = await source('pages/lens/Mcp.vue')

  assert.match(page, /<option value="plugin">/)
  assert.match(page, /listConnections/)
  assert.match(page, /listPlugins/)
  assert.match(page, /getPluginManifest/)
  assert.match(page, /form\.connection_uuid/)
  assert.match(page, /pluginTools/)
  assert.match(page, /connection_uuid:/)
  assert.match(page, /tools:/)
  assert.doesNotMatch(page, /github_read_file/)
  assert.doesNotMatch(page, /plugin_key === 'github'/)
})

test('connection management uses compact cards with summarized scope', async () => {
  const page = await source('pages/lens/Connections.vue')

  assert.match(page, /connections-toolbar/)
  assert.match(page, /connection-card/)
  assert.match(page, /connectionUsageLabels/)
  assert.match(page, /datasourceLabel/)
  assert.match(page, /toolLabel/)
  assert.match(page, /pluginIconUrl/)
  assert.match(page, /connection-usage-summary/)
  assert.match(page, /connectionDetailOpen/)
  assert.match(page, /connection-detail-scope/)
  assert.match(page, /filteredDetailScopeGroups/)
  assert.match(page, /toggleDetailScopeGroup/)
  assert.match(page, /detailScopeSearch/)
  assert.match(page, /detailConnection\.secret_hint/)
})

test('datasource management groups source, target and run information', async () => {
  const page = await source('pages/lens/DataSources.vue')

  assert.match(page, /datasource-toolbar/)
  assert.match(page, /datasource-card/)
  assert.match(page, /pluginIconUrl/)
  assert.match(page, /datasource-source-summary/)
  assert.match(page, /datasource-target-summary/)
  assert.match(page, /datasource-run-summary/)
  assert.doesNotMatch(page, /<table/)
})

test('creation forms do not expose generic active or disabled selectors', async () => {
  const [connections, drawer, detailDrawer] = await Promise.all([
    source('pages/lens/Connections.vue'),
    source('pages/lens/DataSourceFormDrawer.vue'),
    source('pages/lens/DataSourceDetailDrawer.vue')
  ])

  assert.doesNotMatch(connections, /v-model="form\.status"/)
  assert.doesNotMatch(drawer, /v-model="form\.status"/)
  assert.match(connections, /connections\.pause/)
  assert.match(connections, /connections\.resume/)
  assert.match(detailDrawer, /actions\.disableDatasource/)
  assert.match(detailDrawer, /actions\.enableDatasource/)
})

test('datasource wizard presents an explicit configuration summary', async () => {
  const drawer = await source('pages/lens/DataSourceFormDrawer.vue')

  assert.match(drawer, /datasource-wizard-summary/)
  assert.match(drawer, /selectedConnectionScopeSummary/)
  assert.doesNotMatch(drawer, /JSON\.stringify\(selectedConnection\.allowed_scope\)/)
})
