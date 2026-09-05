import assert from 'node:assert/strict'
import test from 'node:test'

import {
  dataSourceBranch,
  dataSourceRepositories,
  dataSourceRepository,
  dataSourceRepositoryUrl,
  isOrganizationDataSource
} from '../src/pages/lens/datasourceHelpers.js'

test('plugin repository fields are used as the datasource resource', () => {
  assert.equal(
    dataSourceRepository({
      plugin_key: 'github',
      datasource_config: { repository: 'oneprolabs/devify' },
      config: {}
    }),
    'oneprolabs/devify'
  )
  assert.equal(
    dataSourceRepository({
      plugin_key: 'gitlab',
      datasource_config: { project: 'hypermotion/mass' },
      config: {}
    }),
    'hypermotion/mass'
  )
})

test('plugin repository URLs include the Connection endpoint', () => {
  assert.equal(
    dataSourceRepositoryUrl(
      {
        plugin_key: 'github',
        datasource_config: { repository: 'oneprolabs/devify' },
        config: {}
      },
      'https://github.com/'
    ),
    'https://github.com/oneprolabs/devify'
  )
  assert.equal(
    dataSourceRepositoryUrl(
      {
        plugin_key: 'gitlab',
        datasource_config: { project: 'hypermotion/mass' },
        config: {}
      },
      'http://gitlab.example.com:20080/'
    ),
    'http://gitlab.example.com:20080/hypermotion/mass'
  )
})

test('multi-resource Plugin datasources expose their first resource and count', () => {
  const row = {
    plugin_key: 'gitlab',
    datasource_config: {
      projects: ['hypermotion/alpha', 'hypermotion/beta']
    },
    config: {}
  }
  assert.equal(dataSourceRepository(row), 'hypermotion/alpha')
  assert.equal(
    dataSourceRepositoryUrl(row, 'https://gitlab.example.com'),
    'https://gitlab.example.com/hypermotion/alpha'
  )
  assert.equal(dataSourceRepositories(row).length, 2)
  assert.equal(isOrganizationDataSource(row), true)
})

test('single-resource Plugin datasources preserve branch details', () => {
  const row = {
    source_type: 'git',
    plugin_key: 'gitlab',
    datasource_config: {
      projects: ['hypermotion/alpha'],
      branch: 'develop'
    },
    config: {}
  }

  assert.equal(isOrganizationDataSource(row), false)
  assert.equal(dataSourceBranch(row), 'develop')
  assert.equal(dataSourceRepositories(row)[0].branch, 'develop')
})

test('legacy and Feishu datasource URLs remain directly readable', () => {
  assert.equal(
    dataSourceRepositoryUrl(
      {
        source_type: 'git',
        config: { repo_url: 'https://example.com/team/repository.git' }
      },
      ''
    ),
    'https://example.com/team/repository.git'
  )
  assert.equal(
    dataSourceRepositoryUrl(
      {
        plugin_key: 'feishu',
        datasource_config: {
          resource_urls: ['https://example.feishu.cn/drive/folder/folder-token']
        },
        config: {}
      },
      'https://open.feishu.cn'
    ),
    'https://example.feishu.cn/drive/folder/folder-token'
  )
})
