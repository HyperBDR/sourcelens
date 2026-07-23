/* eslint-disable no-unused-vars */
// Shared mock data and utilities for Lens prototype v1.1

const MOCK = {
  assistants: [
    {
      uuid: 'a1b2c3d4-0001-0000-0000-000000000001',
      slug: 'code-advisor',
      name: 'Code Advisor',
      capability_type: 'query',
      engine_type: 'claude_code',
      status: 'active',
      datasource_uuids: [
        'ds-0001-0000-0000-000000000001',
        'ds-0004-0000-0000-000000000004'
      ],
      datasources: 2,
      sessions: 14,
      created_at: '2026-05-15T08:00:00Z',
      model_validation: { status: 'ok', checked_at: '2026-06-01T08:00:00Z' }
    },
    {
      uuid: 'a1b2c3d4-0002-0000-0000-000000000002',
      slug: 'api-explorer',
      name: 'API Explorer',
      capability_type: 'query',
      engine_type: 'codex',
      status: 'active',
      datasource_uuids: ['ds-0002-0000-0000-000000000002'],
      datasources: 1,
      sessions: 7,
      created_at: '2026-05-20T10:00:00Z',
      model_validation: {
        status: 'saved_with_error',
        error: 'LENS_ENGINE_NOT_IMPLEMENTED',
        checked_at: '2026-06-01T07:30:00Z'
      }
    },
    {
      uuid: 'a1b2c3d4-0003-0000-0000-000000000003',
      slug: 'legacy-reader',
      name: 'Legacy Reader',
      capability_type: 'query',
      engine_type: 'claude_code',
      status: 'disabled',
      datasource_uuids: [
        'ds-0001-0000-0000-000000000001',
        'ds-0003-0000-0000-000000000003',
        'ds-0005-0000-0000-000000000005'
      ],
      datasources: 3,
      sessions: 2,
      created_at: '2026-04-01T08:00:00Z',
      model_validation: { status: 'unchecked' }
    }
  ],
  datasources: [
    {
      uuid: 'ds-0001-0000-0000-000000000001',
      name: 'sourcelens/backend',
      source_type: 'git',
      status: 'active',
      last_synced_at: '2026-06-01T00:30:00Z',
      assistants_bound: 2,
      config: {
        repo_url: 'https://github.com/example/sourcelens',
        branch: 'main',
        credentials_ref: 'cred-git-001'
      }
    },
    {
      uuid: 'ds-0002-0000-0000-000000000002',
      name: 'API Jira 工单',
      source_type: 'jira',
      status: 'active',
      last_synced_at: '2026-05-31T22:00:00Z',
      assistants_bound: 1,
      config: { base_url: 'https://jira.example.com', auth_scheme: 'token' }
    },
    {
      uuid: 'ds-0003-0000-0000-000000000003',
      name: '本地文档目录',
      source_type: 'local_dir',
      status: 'active',
      last_synced_at: null,
      assistants_bound: 0,
      config: { path: '/var/docs/internal' }
    },
    {
      uuid: 'ds-0004-0000-0000-000000000004',
      name: '飞书知识库',
      source_type: 'feishu',
      status: 'error',
      last_synced_at: '2026-05-28T10:00:00Z',
      assistants_bound: 1,
      config: {
        app_token: 'mock_token_xxx',
        doc_ids: ['doc1', 'doc2'],
        credentials_ref: 'cred-feishu-001'
      }
    },
    {
      uuid: 'ds-0005-0000-0000-000000000005',
      name: '旧版 Confluence',
      source_type: 'confluence',
      status: 'disabled',
      last_synced_at: '2026-04-01T00:00:00Z',
      assistants_bound: 0,
      config: {
        base_url: 'https://confluence.example.com',
        credentials_ref: 'cred-conf-001'
      }
    }
  ],
  skills: [
    {
      uuid: 'sk-0001',
      slug: 'code-search',
      name: 'Code Search',
      enabled: true,
      assistants_bound: 2
    },
    {
      uuid: 'sk-0002',
      slug: 'file-read',
      name: 'File Reader',
      enabled: true,
      assistants_bound: 1
    },
    {
      uuid: 'sk-0003',
      slug: 'test-runner',
      name: 'Test Runner',
      enabled: false,
      assistants_bound: 0
    }
  ],
  mcpServers: [
    {
      uuid: 'mcp-0001',
      name: 'GitHub MCP',
      transport: 'url',
      endpoint: 'https://mcp.example.com/github',
      enabled: true,
      assistants_bound: 1
    },
    {
      uuid: 'mcp-0002',
      name: 'Jira MCP',
      transport: 'stdio',
      endpoint: '',
      enabled: false,
      assistants_bound: 0
    }
  ],
  sessions: [
    {
      uuid: 'sess-0001',
      assistant_slug: 'code-advisor',
      assistant_name: 'Code Advisor',
      title: '如何优化 Celery 任务调度',
      status: 'active',
      created_at: '2026-06-01T09:15:00Z',
      messages: 6
    },
    {
      uuid: 'sess-0002',
      assistant_slug: 'code-advisor',
      assistant_name: 'Code Advisor',
      title: 'SSE 流式接口实现讨论',
      status: 'active',
      created_at: '2026-05-31T14:20:00Z',
      messages: 12
    },
    {
      uuid: 'sess-0003',
      assistant_slug: 'api-explorer',
      assistant_name: 'API Explorer',
      title: 'REST API 路由梳理',
      status: 'archived',
      created_at: '2026-05-29T10:00:00Z',
      messages: 4
    },
    {
      uuid: 'sess-0004',
      assistant_slug: 'code-advisor',
      assistant_name: 'Code Advisor',
      title: '沙箱超时错误排查',
      status: 'failed',
      run_error: 'LENS_SANDBOX_TIMEOUT',
      created_at: '2026-05-30T11:30:00Z',
      messages: 2
    },
    {
      uuid: 'sess-0005',
      assistant_slug: 'code-advisor',
      assistant_name: 'Code Advisor',
      title: 'Django ORM 复杂查询优化',
      status: 'cancelled',
      created_at: '2026-05-30T10:00:00Z',
      messages: 1,
      partialContent:
        '根据代码库分析，Django ORM 的复杂查询优化主要从以下几个角度入手：\n\n**1. select_related 与 prefetch_related**\n\n对于外键关联查询...'
    }
  ],
  globalSettings: [
    {
      key: 'sandbox.defaults.timeout',
      value: 120,
      description: '沙箱默认超时秒数（必须 > 0，建议 30–3600）'
    },
    {
      key: 'sandbox.defaults.resource_limits',
      value: { cpu: '0.5', memory: '512m', pids: 50 },
      description: '沙箱默认资源限制'
    },
    { key: 'retention.run_days', value: 30, description: 'Run 记录保留天数' }
  ],
  scheduledTasks: [
    {
      id: 'st-0001',
      name: 'sandbox_cleanup',
      description: '清理过期沙箱容器',
      schedule: '*/15 * * * *',
      last_status: 'success',
      last_run: '2026-06-01T09:45:00Z',
      next_run: '2026-06-01T10:00:00Z'
    },
    {
      id: 'st-0002',
      name: 'run_retention',
      description: '清理过期 Run 记录（保留 retention.run_days 天）',
      schedule: '0 2 * * *',
      last_status: 'failed',
      last_run: '2026-06-01T02:00:00Z',
      last_error: 'DB connection timeout after 30s',
      next_run: '2026-06-02T02:00:00Z'
    }
  ],
  // D4: Lens sync task executions — GET /api/v1/tasks/executions/?module=lens
  syncExecutions: [
    {
      uuid: 'exec-0001',
      datasource_uuid: 'ds-0001-0000-0000-000000000001',
      datasource_name: 'sourcelens/backend',
      trigger: 'scheduled',
      status: 'STARTED',
      progress: 45,
      started_at: '2026-06-01T10:15:00Z',
      finished_at: null,
      error_code: null,
      error_message: null
    },
    {
      uuid: 'exec-0002',
      datasource_uuid: 'ds-0002-0000-0000-000000000002',
      datasource_name: 'API Jira 工单',
      trigger: 'manual',
      status: 'RETRY',
      progress: 0,
      started_at: '2026-06-01T09:55:00Z',
      finished_at: null,
      error_code: 'NETWORK_TIMEOUT',
      error_message: '连接超时，正在重试 (3/5)：jira.example.com:443'
    },
    {
      uuid: 'exec-0003',
      datasource_uuid: 'ds-0004-0000-0000-000000000004',
      datasource_name: '飞书知识库',
      trigger: 'manual',
      status: 'FAILURE',
      progress: 0,
      started_at: '2026-05-28T10:00:00Z',
      finished_at: '2026-05-28T10:01:15Z',
      error_code: 'CRED_INVALID',
      error_message:
        '凭证已失效：App Token 已过期，请前往数据源管理更新凭证引用'
    },
    {
      uuid: 'exec-0004',
      datasource_uuid: 'ds-0005-0000-0000-000000000005',
      datasource_name: '旧版 Confluence',
      trigger: 'scheduled',
      status: 'REVOKED',
      progress: 30,
      started_at: '2026-05-30T02:00:00Z',
      finished_at: '2026-05-30T02:03:00Z',
      error_code: 'WORKER_RESTART',
      error_message: null
    },
    {
      uuid: 'exec-0005',
      datasource_uuid: 'ds-0002-0000-0000-000000000002',
      datasource_name: 'API Jira 工单',
      trigger: 'scheduled',
      status: 'SUCCESS',
      progress: 100,
      started_at: '2026-05-31T22:00:00Z',
      finished_at: '2026-05-31T22:05:30Z',
      error_code: null,
      error_message: null
    }
  ],
  // Per-datasource sync button state (derived from latest execution)
  datasourceSyncState: {
    'ds-0001-0000-0000-000000000001': {
      status: 'STARTED',
      progress: 45,
      last_synced_at: '2026-06-01T00:30:00Z',
      error_code: null,
      error_message: null
    },
    'ds-0002-0000-0000-000000000002': {
      status: 'RETRY',
      progress: 0,
      last_synced_at: '2026-05-31T22:00:00Z',
      error_code: 'NETWORK_TIMEOUT',
      error_message: '连接超时，正在重试 (3/5)'
    },
    'ds-0003-0000-0000-000000000003': null,
    'ds-0004-0000-0000-000000000004': {
      status: 'FAILURE',
      progress: 0,
      last_synced_at: '2026-05-28T10:00:00Z',
      error_code: 'CRED_INVALID',
      error_message:
        '凭证已失效：App Token 已过期，请前往数据源管理更新凭证引用'
    },
    'ds-0005-0000-0000-000000000005': {
      status: 'REVOKED',
      progress: 30,
      last_synced_at: '2026-04-01T00:00:00Z',
      error_code: 'WORKER_RESTART',
      error_message: null
    }
  }
}

function formatDate(isoString) {
  if (!isoString) return '—'
  const d = new Date(isoString)
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  })
}
