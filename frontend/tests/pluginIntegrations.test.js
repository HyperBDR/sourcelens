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
  assert.doesNotMatch(drawer, /githubConnections/)
  assert.doesNotMatch(drawer, /githubPluginTools/)
  assert.doesNotMatch(drawer, /githubPluginManifest/)
})

test('manifest resource options preserve an existing dependent value', async () => {
  const renderer = await source('components/lens/ManifestSchemaForm.vue')

  assert.match(renderer, /field\.depends_on/)
  assert.match(renderer, /item\?\.options/)
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
  const drawer = await source('pages/lens/DataSourceFormDrawer.vue')

  assert.match(drawer, /ManifestSchemaForm/)
  assert.match(drawer, /datasourceSchema/)
  assert.match(drawer, /pluginResources/)
  assert.match(drawer, /updatePluginConfig/)
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
