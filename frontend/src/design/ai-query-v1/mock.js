export const navTabs = [
  {
    key: 'projects',
    label: '项目配置',
    hint: 'CRUD / 接口映射 / 同步任务实例'
  },
  {
    key: 'query',
    label: '查询与流式',
    hint: 'SSE / 取消 / 部分答案保留'
  },
  {
    key: 'system',
    label: '系统状态',
    hint: '队列 / 调度 / 健康面板'
  }
]

export const queryOutcomes = [
  {
    key: 'success',
    label: '正常流式',
    hint: '完整答案在流式结束后落地'
  },
  {
    key: 'partial',
    label: '部分答案保留',
    hint: '失败时保留已生成片段'
  },
  {
    key: 'timeout',
    label: '超时失败',
    hint: '展示 LENS_SANDBOX_TIMEOUT'
  }
]

export const apiContracts = [
  { method: 'GET', path: '/api/v1/projects', purpose: '项目列表与详情卡片' },
  { method: 'POST', path: '/api/v1/projects', purpose: '新建项目配置' },
  { method: 'PATCH', path: '/api/v1/projects/:id', purpose: '编辑项目配置' },
  { method: 'DELETE', path: '/api/v1/projects/:id', purpose: '删除项目配置' },
  {
    method: 'POST',
    path: '/api/v1/projects/:id/sync',
    purpose: '手动触发同步任务实例'
  },
  {
    method: 'POST',
    path: '/api/v1/queries/stream',
    purpose: '提交问题并接收 SSE 流式结果'
  },
  {
    method: 'GET',
    path: '/api/v1/system/status',
    purpose: '系统健康与调度概览'
  }
]

export const scheduledTasks = [
  {
    name: 'lensnode_cleanup',
    schedule: '*/15 * * * *',
    lastStatus: 'success',
    lastRun: '2026-06-01T09:45:00Z',
    nextRun: '2026-06-01T10:00:00Z',
    note: '清理超时 LensNode Run'
  },
  {
    name: 'run_retention',
    schedule: '0 2 * * *',
    lastStatus: 'failed',
    lastRun: '2026-06-01T02:00:00Z',
    nextRun: '2026-06-02T02:00:00Z',
    note: '清理过期 Run 记录',
    lastError: 'DB connection timeout after 30s'
  }
]

export const projectSeed = [
  {
    id: 'proj-core',
    name: 'SourceLens 核心仓库',
    sourceType: 'Git',
    sourceUrl: 'https://github.com/HyperBDR/sourcelens.git',
    authRef: 'git-token-ref-001',
    localPath: '/opt/sourcelens/core',
    refreshInterval: 15,
    description:
      '用于检索 API、任务、配置文档的主项目，包含 AI Query 的后端接口定义。',
    syncState: 'success',
    syncPolicy: 'success',
    lastSyncedAt: '2026-06-01T10:18:00Z',
    lastSyncError: '',
    owner: '管理员',
    permissions: ['查询', '编辑', '手动同步'],
    syncHistory: [
      {
        id: 'sync-001',
        trigger: '定时',
        status: 'success',
        startedAt: '2026-06-01T10:18:00Z',
        finishedAt: '2026-06-01T10:18:42Z',
        progress: 100,
        message: '增量拉取完成，更新 18 个文件'
      },
      {
        id: 'sync-002',
        trigger: '手动',
        status: 'success',
        startedAt: '2026-05-31T22:05:00Z',
        finishedAt: '2026-05-31T22:05:33Z',
        progress: 100,
        message: '完成，等待下一次调度'
      },
      {
        id: 'sync-003',
        trigger: '定时',
        status: 'failed',
        startedAt: '2026-05-31T08:05:00Z',
        finishedAt: '2026-05-31T08:06:20Z',
        progress: 0,
        message: '网络抖动导致 git fetch 失败',
        errorCode: 'NETWORK_TIMEOUT'
      }
    ]
  },
  {
    id: 'proj-feishu',
    name: '飞书知识库',
    sourceType: '飞书文档',
    sourceUrl: 'https://example.feishu.cn/wiki/xxxx',
    authRef: 'feishu-app-token-ref-002',
    localPath: '/opt/sourcelens/feishu',
    refreshInterval: 30,
    description:
      '团队文档与操作手册来源。该数据源保留脱敏凭证引用，不显示真实 Token。',
    syncState: 'failed',
    syncPolicy: 'failed',
    lastSyncedAt: '2026-05-28T10:00:00Z',
    lastSyncError: '凭证已失效：App Token 已过期，请更新凭证引用',
    owner: '管理员',
    permissions: ['查询', '编辑', '手动同步'],
    syncHistory: [
      {
        id: 'sync-101',
        trigger: '定时',
        status: 'failed',
        startedAt: '2026-05-28T09:58:00Z',
        finishedAt: '2026-05-28T10:00:15Z',
        progress: 0,
        message: '凭证失效，任务失败',
        errorCode: 'CRED_INVALID'
      },
      {
        id: 'sync-102',
        trigger: '手动',
        status: 'success',
        startedAt: '2026-05-27T10:00:00Z',
        finishedAt: '2026-05-27T10:00:20Z',
        progress: 100,
        message: '同步成功'
      }
    ]
  },
  {
    id: 'proj-archive',
    name: '归档资料库',
    sourceType: '本地目录',
    sourceUrl: 'file:///data/archive/docs',
    authRef: 'local-folder',
    localPath: '/opt/sourcelens/archive',
    refreshInterval: 1440,
    description:
      '历史归档资料，仅保留查询入口，不再持续同步。用于展示空态和停用态。',
    syncState: 'disabled',
    syncPolicy: 'disabled',
    lastSyncedAt: null,
    lastSyncError: '',
    owner: '只读用户',
    permissions: ['查询'],
    syncHistory: []
  }
]

export const modelOptions = ['claude-4.1', 'codex-3.5', 'gpt-4.1']

export const questionPresets = [
  '请解释为什么同步任务应该归属于数据源管理。',
  '如何展示 SSE 流式查询的加载、取消与失败态？',
  '管理员和普通用户在原型里分别看见什么？'
]

export function clone(value) {
  return JSON.parse(JSON.stringify(value))
}

export function createProjectDraft(project = null) {
  return {
    id: project?.id || `proj-${Date.now()}`,
    name: project?.name || '',
    sourceType: project?.sourceType || 'Git',
    sourceUrl: project?.sourceUrl || '',
    authRef: project?.authRef || '',
    localPath: project?.localPath || '',
    refreshInterval: project?.refreshInterval || 15,
    description: project?.description || ''
  }
}

export function formatClock(iso) {
  if (!iso) return '未同步'
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(iso))
}

export function formatLongClock(iso) {
  if (!iso) return '未记录'
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  }).format(new Date(iso))
}

export function normalizeBadgeStatus(status) {
  const map = {
    success: 'success',
    failed: 'failed',
    processing: 'processing',
    pending: 'pending',
    completed: 'completed',
    enabled: 'enabled',
    disabled: 'disabled',
    queued: 'pending',
    running: 'processing',
    cancelled: 'disabled',
    success_sync: 'success'
  }

  return map[status] || 'pending'
}
