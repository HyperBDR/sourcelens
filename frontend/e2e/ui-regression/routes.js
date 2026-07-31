/**
 * Per-project route registry — the ONLY hand-curated input to the engine, and
 * the part an AI generates from `src/router`, the API client call sites, and
 * the locale files. Everything else (mock layer, assertion battery, walk) is
 * project-agnostic.
 *
 * Each entry:
 *   id            stable label used in test names + screenshot filenames
 *   path          concrete URL to visit (params filled with fixture values)
 *   seedStorage   extra localStorage keys needed to render (optional)
 *   ignoreConsole RegExp[] of known-benign console lines to suppress (optional)
 *   mocks         { '<pathname glob>': (state) => response } — forward+reverse
 *
 * Spike scope: 3 representative shapes — a public form, a data-driven list,
 * and an authenticated landing. Scale by generating more entries from code.
 */

const user = {
  id: 1,
  username: 'tester',
  is_staff: false,
  is_superuser: false,
  features: ['workspace'],
  permissions: []
}

// Admin/staff user — required for the management pages to render instead of
// bouncing to login or showing a permission wall.
const admin = {
  id: 1,
  username: 'admin',
  is_staff: true,
  is_superuser: true,
  features: ['workspace', 'llm', 'tasks', 'notifier'],
  permissions: ['*']
}

const qaItem = {
  uuid: 'qa-1',
  question: 'How do I reset a node?',
  answer: 'Open the node page and click Reset.',
  created_at: '2026-07-28T02:00:00Z'
}

function listByState(state, items) {
  if (state === 'error') return { status: 500, json: { detail: 'boom' } }
  return { status: 200, json: state === 'empty' ? [] : items }
}

export const routes = [
  {
    id: 'login',
    path: '/login',
    // Proof-of-exercise sentinels: a locale-specific string that MUST be on
    // the page for that locale. If the language axis silently fails to apply,
    // the sentinel is absent and the cell goes red — deterministically, with
    // no human eyeballing and no AI judging a screenshot.
    sentinels: { en: 'Sign in to SourceLens', 'zh-CN': '登录 SourceLens' },
    // Intent per locale — what the visual oracle should confirm on screen.
    intent: {
      en: 'English login form: title "Sign in to SourceLens", an email field, and a "Send code" button.',
      'zh-CN':
        '中文登录页：标题"登录 SourceLens"，一个邮箱输入框，一个"发送验证码"按钮。'
    },
    mocks: {
      '/api/v1/auth/user': () => ({ status: 401, json: { detail: 'anon' } })
    }
  },
  {
    id: 'public-qa-list',
    path: '/lens/assistants/demo/qa',
    intent: {
      en: 'Public Q&A page with a "Public Q&A" heading; either a list of Q&A entries or an empty-state message.',
      'zh-CN': '公开问答页，带"公开问答"标题；显示问答列表或空状态提示。'
    },
    mocks: {
      '/api/lens/public/assistants/*': () => ({
        status: 200,
        json: { slug: 'demo', name: 'Demo Assistant', status: 'active' }
      }),
      '/api/lens/assistants/*/shared-qa*': (state) =>
        listByState(state, [qaItem]),
      '/api/lens/shares*': (state) => listByState(state, [qaItem])
    }
  },
  {
    id: 'dashboard',
    path: '/dashboard',
    authed: true,
    intent: {
      en: 'Assistant chat page for a logged-in user, in English: a left sidebar with "New session", a main area with an "Ask anything" input box.',
      'zh-CN':
        '已登录用户的助手对话页，界面为中文：左侧有"新建会话"侧栏，主区域有一个"输入问题"的输入框。'
    },
    mocks: {
      '/api/v1/auth/user': () => ({ status: 200, json: user }),
      '/api/lens/assistants/': (state) =>
        listByState(state, [
          { uuid: 'a-1', slug: 'demo', name: 'Demo', status: 'active' }
        ])
    }
  },
  {
    id: 'llm-config',
    path: '/llm/config',
    authed: true,
    intent: {
      en: 'Admin LLM configuration page, in English (a list or form for model configs).',
      'zh-CN': '管理台 LLM 配置页，界面为中文（模型配置的列表或表单）。'
    },
    mocks: {
      '/api/v1/auth/user': () => ({ status: 200, json: admin }),
      '/api/v1/admin/llm-config/all*': (state) => listByState(state, []),
      '/api/v1/admin/llm-config/providers*': () => ({ status: 200, json: [] })
    }
  },
  {
    id: 'llm-stats',
    path: '/llm/stats',
    authed: true,
    intent: {
      en: 'Admin LLM usage/statistics page, in English (charts or a stats summary).',
      'zh-CN': '管理台 LLM 用量/统计页，界面为中文（图表或统计概览）。'
    },
    mocks: {
      '/api/v1/auth/user': () => ({ status: 200, json: admin }),
      '/api/v1/admin/**': (state) => listByState(state, [])
    }
  },
  {
    id: 'task-management',
    path: '/task-management/list',
    authed: true,
    intent: {
      en: 'Admin task management list page, in English (a table or list of tasks).',
      'zh-CN': '管理台任务管理列表页，界面为中文（任务的表格或列表）。'
    },
    mocks: {
      '/api/v1/auth/user': () => ({ status: 200, json: admin }),
      '/api/v1/tasks/**': (state) => listByState(state, [])
    }
  },
  {
    id: 'notifier-channels',
    path: '/notifier/channels',
    authed: true,
    intent: {
      en: 'Admin notification channels page, in English (a list of channels or an empty state).',
      'zh-CN': '管理台通知渠道页，界面为中文（渠道列表或空状态）。'
    },
    mocks: {
      '/api/v1/auth/user': () => ({ status: 200, json: admin }),
      '/api/v1/admin/notifications/**': (state) => listByState(state, [])
    }
  }
]
