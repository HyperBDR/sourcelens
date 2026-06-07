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

// Per-assistant MCP bindings (for assistant edit modal)
const MOCK_ASSISTANT_MCP_BINDINGS = {
  'a1b2c3d4-0001-0000-0000-000000000001': [
    {
      mcp_uuid: 'mcp-0001',
      enabled: true,
      load_config: false,
      scope: 'session'
    }
  ],
  'a1b2c3d4-0002-0000-0000-000000000002': [],
  'a1b2c3d4-0003-0000-0000-000000000003': []
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

function statusBadge(status) {
  const map = {
    active: 'bg-green-100 text-green-800',
    disabled: 'bg-gray-100 text-gray-600',
    error: 'bg-red-100 text-red-800',
    archived: 'bg-yellow-100 text-yellow-800',
    queued: 'bg-blue-100 text-blue-800',
    running: 'bg-indigo-100 text-indigo-800',
    done: 'bg-green-100 text-green-800',
    failed: 'bg-red-100 text-red-800',
    cancelled: 'bg-orange-100 text-orange-700',
    success: 'bg-green-100 text-green-800'
  }
  const label = {
    active: '运行中',
    disabled: '已禁用',
    error: '错误',
    archived: '已归档',
    queued: '排队中',
    running: '运行中',
    done: '完成',
    failed: '失败',
    cancelled: '已取消',
    success: '成功'
  }
  return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${map[status] || 'bg-gray-100 text-gray-600'}">${label[status] || status}</span>`
}

function engineBadge(engine) {
  const map = {
    claude_code: 'bg-violet-100 text-violet-800',
    codex: 'bg-sky-100 text-sky-800',
    http_direct: 'bg-gray-100 text-gray-500',
    deepagent: 'bg-gray-100 text-gray-500'
  }
  return `<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-mono ${map[engine] || 'bg-gray-100 text-gray-600'}">${engine}</span>`
}

// M1: model validation badge with real states
function modelValidationBadge(mv) {
  if (!mv) return '<span class="text-xs text-gray-400">—</span>'
  if (mv.status === 'ok') {
    return `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800" title="校验时间: ${formatDate(mv.checked_at)}">
      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>校验通过</span>`
  }
  if (mv.status === 'saved_with_error') {
    return `<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800" title="错误: ${mv.error}">
      <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>已保存（校验失败）</span>`
  }
  return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-500">未校验</span>`
}

// D4: sync task status badge (6 states)
function syncTaskStatusBadge(status) {
  const cfg = {
    PENDING: { cls: 'bg-blue-100 text-blue-700', label: '排队中', spin: true },
    STARTED: {
      cls: 'bg-indigo-100 text-indigo-700',
      label: '同步中…',
      spin: true
    },
    RETRY: {
      cls: 'bg-yellow-100 text-yellow-700',
      label: '重试中…',
      spin: true
    },
    SUCCESS: {
      cls: 'bg-green-100 text-green-700',
      label: '已完成',
      spin: false
    },
    FAILURE: { cls: 'bg-red-100 text-red-700', label: '失败', spin: false },
    REVOKED: {
      cls: 'bg-amber-100 text-amber-700',
      label: '已撤销',
      spin: false
    }
  }
  const c = cfg[status] || {
    cls: 'bg-gray-100 text-gray-600',
    label: status,
    spin: false
  }
  const spinner = c.spin
    ? `<svg class="animate-spin w-3 h-3 mr-1 flex-shrink-0" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>`
    : ''
  return `<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${c.cls}">${spinner}${c.label}</span>`
}

function calcDuration(started_at, finished_at) {
  if (!started_at) return '—'
  const s = new Date(started_at)
  const f = finished_at ? new Date(finished_at) : null
  if (!f) return '<span class="text-indigo-600">进行中…</span>'
  const secs = Math.round((f - s) / 1000)
  if (secs < 60) return `${secs}s`
  const m = Math.floor(secs / 60),
    r = secs % 60
  return r > 0 ? `${m}m ${r}s` : `${m}m`
}

function showToast(msg, type = 'success') {
  const el = document.createElement('div')
  const color =
    type === 'success'
      ? 'bg-green-600'
      : type === 'error'
        ? 'bg-red-600'
        : type === 'warn'
          ? 'bg-orange-500'
          : 'bg-blue-600'
  const icon =
    type === 'success'
      ? 'M5 13l4 4L19 7'
      : type === 'warn'
        ? 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z'
        : 'M6 18L18 6M6 6l12 12'
  el.className = `fixed top-4 right-4 z-50 ${color} text-white px-4 py-3 rounded-lg shadow-lg text-sm flex items-center gap-2 transition-all`
  el.innerHTML = `<svg class="w-4 h-4 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${icon}"/></svg>${msg}`
  document.body.appendChild(el)
  setTimeout(() => {
    el.style.opacity = '0'
    setTimeout(() => el.remove(), 300)
  }, 2800)
}

function openModal(id) {
  document.getElementById(id)?.classList.remove('hidden')
}
function closeModal(id) {
  document.getElementById(id)?.classList.add('hidden')
}

function getAssistantDatasourceSummary(assistant) {
  const datasourceIds = assistant.datasource_uuids || []
  if (datasourceIds.length === 0) {
    return {
      total: assistant.datasources || 0,
      active: assistant.datasources || 0,
      disabled: 0
    }
  }
  const bound = datasourceIds
    .map((uuid) => MOCK.datasources.find((ds) => ds.uuid === uuid))
    .filter(Boolean)
  const disabled = bound.filter((ds) => ds.status === 'disabled').length
  return {
    total: bound.length,
    active: bound.length - disabled,
    disabled
  }
}
