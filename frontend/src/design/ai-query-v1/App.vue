<template>
  <div class="min-h-screen bg-slate-950 text-slate-100">
    <div class="pointer-events-none fixed inset-0 overflow-hidden">
      <div
        class="absolute left-[-12rem] top-[-10rem] h-80 w-80 rounded-full bg-cyan-500/20 blur-3xl"
      />
      <div
        class="absolute right-[-8rem] top-24 h-72 w-72 rounded-full bg-fuchsia-500/20 blur-3xl"
      />
      <div
        class="absolute bottom-[-10rem] left-1/3 h-96 w-96 rounded-full bg-emerald-500/10 blur-3xl"
      />
    </div>

    <div class="relative mx-auto max-w-[1600px] px-4 py-6 lg:px-6 xl:px-8">
      <header
        class="mb-6 overflow-hidden rounded-[28px] border border-white/10 bg-white/6 shadow-2xl backdrop-blur-xl"
      >
        <div class="grid gap-6 px-6 py-6 xl:grid-cols-[minmax(0,1fr)_auto]">
          <div class="space-y-4">
            <div class="flex flex-wrap items-center gap-3">
              <span
                class="rounded-full border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.24em] text-cyan-200"
              >
                Dev-only prototype
              </span>
              <span
                class="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-200"
              >
                Vue + Tailwind
              </span>
              <span
                class="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-slate-200"
              >
                数据源管理 -> 查询 -> 系统状态
              </span>
            </div>

            <div class="space-y-2">
              <h1 class="text-3xl font-semibold tracking-tight text-white">
                AI Query 系统前端原型
              </h1>
              <p class="max-w-4xl text-sm leading-6 text-slate-300">
                本页是 dev-only 的可运行原型，使用 Vue + Tailwind 构建。
                它把项目配置、同步任务实例、SSE 查询流和系统状态放进同一
                套交互骨架，避免静态 HTML 带来的版式失真。
              </p>
            </div>

            <div class="grid gap-3 md:grid-cols-4">
              <div
                v-for="metric in topMetrics"
                :key="metric.label"
                class="rounded-2xl border border-white/10 bg-slate-900/70 p-4"
              >
                <div class="text-xs text-slate-400">
                  {{ metric.label }}
                </div>
                <div class="mt-2 text-2xl font-semibold text-white">
                  {{ metric.value }}
                </div>
                <div class="mt-1 text-xs text-slate-500">
                  {{ metric.help }}
                </div>
              </div>
            </div>
          </div>

          <div class="space-y-4 xl:w-[360px]">
            <div class="rounded-3xl border border-white/10 bg-slate-900/80 p-4">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <div
                    class="text-xs uppercase tracking-[0.2em] text-slate-500"
                  >
                    当前视图
                  </div>
                  <div class="mt-1 text-base font-semibold text-white">
                    {{ activeTabLabel }}
                  </div>
                </div>
                <StatusBadge :status="currentSystemBadge" />
              </div>

              <div class="mt-4 flex flex-wrap gap-2">
                <button
                  v-for="roleOption in roleOptions"
                  :key="roleOption.key"
                  class="rounded-full px-3 py-1.5 text-xs font-semibold transition"
                  :class="
                    activeRole === roleOption.key
                      ? 'bg-cyan-400 text-slate-950'
                      : 'bg-white/10 text-slate-300 hover:bg-white/12'
                  "
                  @click="activeRole = roleOption.key"
                >
                  {{ roleOption.label }}
                </button>
              </div>

              <div class="mt-4 grid gap-2">
                <button
                  v-for="tab in navTabs"
                  :key="tab.key"
                  class="group flex items-start justify-between rounded-2xl border px-3 py-2 text-left transition"
                  :class="
                    activeTab === tab.key
                      ? 'border-cyan-400/50 bg-cyan-400/10'
                      : 'border-white/10 bg-white/5 hover:bg-white/10'
                  "
                  @click="activeTab = tab.key"
                >
                  <div>
                    <div class="text-sm font-medium text-white">
                      {{ tab.label }}
                    </div>
                    <div class="mt-1 text-xs text-slate-400">
                      {{ tab.hint }}
                    </div>
                  </div>
                  <span
                    class="mt-0.5 rounded-full border border-white/10 px-2 py-0.5 text-[10px] uppercase tracking-[0.2em] text-slate-400"
                  >
                    {{ tab.key }}
                  </span>
                </button>
              </div>
            </div>

            <div class="rounded-3xl border border-white/10 bg-slate-900/80 p-4">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <div
                    class="text-xs uppercase tracking-[0.2em] text-slate-500"
                  >
                    接口期望
                  </div>
                  <div class="mt-1 text-sm font-semibold text-white">
                    与 CTO 设计对齐的 API 约定
                  </div>
                </div>
                <span
                  class="rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-200"
                >
                  Mock
                </span>
              </div>

              <div class="mt-4 space-y-2">
                <div
                  v-for="contract in apiContracts"
                  :key="`${contract.method}-${contract.path}`"
                  class="rounded-2xl border border-white/10 bg-white/5 p-3"
                >
                  <div class="flex items-center justify-between gap-2">
                    <div class="flex items-center gap-2">
                      <span
                        class="rounded-full bg-cyan-400/15 px-2.5 py-1 text-[11px] font-semibold text-cyan-200"
                      >
                        {{ contract.method }}
                      </span>
                      <span class="font-mono text-xs text-slate-200">
                        {{ contract.path }}
                      </span>
                    </div>
                  </div>
                  <div class="mt-1 text-xs leading-5 text-slate-400">
                    {{ contract.purpose }}
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      <div class="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)_360px]">
        <aside class="space-y-6">
          <BaseCard
            padding="none"
            class="overflow-hidden border border-white/10 bg-slate-900/80 shadow-none"
          >
            <template #header>
              <div class="flex items-center justify-between gap-3">
                <div>
                  <h2 class="text-base font-semibold text-white">数据源目录</h2>
                  <p class="mt-1 text-xs text-slate-400">
                    搜索、选中、编辑、删除与同步实例都从这里发起。
                  </p>
                </div>
                <StatusBadge
                  :status="visibleProjects.length ? 'success' : 'disabled'"
                />
              </div>
            </template>

            <div class="space-y-4 p-4">
              <BaseInput
                v-model="projectSearch"
                label="搜索"
                placeholder="按名称、来源类型、路径搜索"
              />

              <div
                v-if="visibleProjects.length"
                class="max-h-[calc(100vh-20rem)] space-y-3 overflow-y-auto pr-1"
              >
                <button
                  v-for="project in visibleProjects"
                  :key="project.id"
                  class="w-full rounded-3xl border p-4 text-left transition"
                  :class="
                    activeProjectId === project.id
                      ? 'border-cyan-400/50 bg-cyan-400/10'
                      : 'border-white/10 bg-white/5 hover:border-white/20 hover:bg-white/10'
                  "
                  @click="activeProjectId = project.id"
                >
                  <div class="flex items-start justify-between gap-3">
                    <div class="min-w-0">
                      <div class="truncate text-sm font-semibold text-white">
                        {{ project.name }}
                      </div>
                      <div class="mt-1 text-xs text-slate-400">
                        {{ project.sourceType }} · {{ project.owner }}
                      </div>
                    </div>
                    <StatusBadge
                      :status="normalizeBadgeStatus(project.syncState)"
                    />
                  </div>

                  <div class="mt-3 space-y-2">
                    <div
                      class="text-xs text-slate-300 line-clamp-2 break-words"
                    >
                      {{ project.description }}
                    </div>
                    <div
                      class="rounded-2xl bg-slate-950/70 px-3 py-2 text-xs text-slate-400"
                    >
                      <span class="block truncate font-mono text-slate-300">
                        {{ project.localPath }}
                      </span>
                    </div>
                  </div>

                  <div
                    class="mt-3 flex items-center justify-between gap-2 text-xs text-slate-400"
                  >
                    <span>最近同步</span>
                    <span>{{ formatClock(project.lastSyncedAt) }}</span>
                  </div>
                </button>
              </div>

              <div
                v-else
                class="rounded-3xl border border-dashed border-white/15 bg-white/4 px-4 py-10 text-center"
              >
                <div class="text-sm font-medium text-white">
                  没有匹配的数据源
                </div>
                <div class="mt-1 text-xs leading-5 text-slate-400">
                  这是列表空态，清空搜索条件后可恢复。
                </div>
                <div class="mt-4">
                  <BaseButton
                    variant="outline"
                    size="sm"
                    @click="projectSearch = ''"
                  >
                    清空筛选
                  </BaseButton>
                </div>
              </div>
            </div>
          </BaseCard>

          <BaseCard
            padding="none"
            class="overflow-hidden border border-white/10 bg-slate-900/80 shadow-none"
          >
            <template #header>
              <div class="flex items-center justify-between gap-3">
                <div>
                  <h2 class="text-base font-semibold text-white">权限提示</h2>
                  <p class="mt-1 text-xs text-slate-400">
                    普通用户与管理员的能力差异。
                  </p>
                </div>
              </div>
            </template>

            <div class="space-y-3 p-4 text-sm text-slate-300">
              <div
                class="rounded-2xl border border-white/10 bg-white/5 px-3 py-3"
              >
                <div class="font-medium text-white">普通用户</div>
                <div class="mt-1 text-xs leading-5 text-slate-400">
                  可查询、可查看同步历史、可看到只读的配置卡片。
                </div>
              </div>
              <div
                class="rounded-2xl border border-white/10 bg-white/5 px-3 py-3"
              >
                <div class="font-medium text-white">管理员</div>
                <div class="mt-1 text-xs leading-5 text-slate-400">
                  可新建、编辑、删除数据源，并手动触发同步实例。
                </div>
              </div>
            </div>
          </BaseCard>
        </aside>

        <main class="space-y-6">
          <BaseCard
            padding="none"
            class="overflow-hidden border border-white/10 bg-slate-900/80 shadow-none"
          >
            <template #header>
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 class="text-base font-semibold text-white">
                    {{ activeTabLabel }}
                  </h2>
                  <p class="mt-1 text-xs text-slate-400">
                    {{ activeTabHint }}
                  </p>
                </div>
                <div class="flex flex-wrap items-center gap-2">
                  <BaseButton
                    v-for="preset in questionPresets"
                    :key="preset"
                    variant="ghost"
                    size="sm"
                    @click="fillQuestion(preset)"
                  >
                    示例问题
                  </BaseButton>
                </div>
              </div>
            </template>

            <div class="border-b border-white/10 px-4 pt-4">
              <div class="flex flex-wrap gap-2">
                <button
                  v-for="tab in navTabs"
                  :key="tab.key"
                  class="rounded-full px-4 py-2 text-sm font-semibold transition"
                  :class="
                    activeTab === tab.key
                      ? 'bg-cyan-400 text-slate-950'
                      : 'bg-white/6 text-slate-300 hover:bg-white/12'
                  "
                  @click="activeTab = tab.key"
                >
                  {{ tab.label }}
                </button>
              </div>
            </div>

            <div class="p-4">
              <section v-if="activeTab === 'projects'" class="space-y-6">
                <div
                  v-if="activeRole === 'user'"
                  class="rounded-3xl border border-cyan-400/30 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-100"
                >
                  你当前是普通用户，配置区域为只读。你仍然可以查看同步实例和项目说明。
                </div>

                <div
                  class="grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(0,0.95fr)]"
                >
                  <BaseCard
                    padding="none"
                    class="overflow-hidden border border-white/10 bg-white/4 shadow-none"
                  >
                    <template #header>
                      <div class="flex items-center justify-between gap-3">
                        <div>
                          <h3 class="text-sm font-semibold text-white">
                            项目配置卡片
                          </h3>
                          <p class="mt-1 text-xs text-slate-400">
                            展示项目字段、接口预期与可见性。
                          </p>
                        </div>
                        <div class="flex flex-wrap gap-2">
                          <BaseButton
                            v-if="activeRole === 'admin'"
                            variant="secondary"
                            size="sm"
                            @click="openDrawer('create')"
                          >
                            新建
                          </BaseButton>
                          <BaseButton
                            v-if="activeRole === 'admin'"
                            variant="outline"
                            size="sm"
                            @click="openDrawer('edit', currentProject)"
                          >
                            编辑
                          </BaseButton>
                          <BaseButton
                            v-if="activeRole === 'admin'"
                            variant="danger"
                            size="sm"
                            @click="askDelete(currentProject)"
                          >
                            删除
                          </BaseButton>
                        </div>
                      </div>
                    </template>

                    <div class="space-y-4 p-4">
                      <div class="grid gap-3 md:grid-cols-2">
                        <div
                          class="rounded-2xl border border-white/10 bg-slate-950/70 p-3"
                        >
                          <div class="text-xs text-slate-500">名称</div>
                          <div class="mt-1 text-sm font-medium text-white">
                            {{ currentProject?.name || '无可用项目' }}
                          </div>
                        </div>
                        <div
                          class="rounded-2xl border border-white/10 bg-slate-950/70 p-3"
                        >
                          <div class="text-xs text-slate-500">来源类型</div>
                          <div class="mt-1 text-sm font-medium text-white">
                            {{ currentProject?.sourceType || '-' }}
                          </div>
                        </div>
                        <div
                          class="rounded-2xl border border-white/10 bg-slate-950/70 p-3"
                        >
                          <div class="text-xs text-slate-500">来源地址</div>
                          <div
                            class="mt-1 break-words font-mono text-xs text-slate-200"
                          >
                            {{ currentProject?.sourceUrl || '-' }}
                          </div>
                        </div>
                        <div
                          class="rounded-2xl border border-white/10 bg-slate-950/70 p-3"
                        >
                          <div class="text-xs text-slate-500">本地同步路径</div>
                          <div
                            class="mt-1 break-words font-mono text-xs text-slate-200"
                          >
                            {{ currentProject?.localPath || '-' }}
                          </div>
                        </div>
                        <div
                          class="rounded-2xl border border-white/10 bg-slate-950/70 p-3"
                        >
                          <div class="text-xs text-slate-500">刷新周期</div>
                          <div class="mt-1 text-sm font-medium text-white">
                            每 {{ currentProject?.refreshInterval || '-' }} 分钟
                          </div>
                        </div>
                        <div
                          class="rounded-2xl border border-white/10 bg-slate-950/70 p-3"
                        >
                          <div class="text-xs text-slate-500">凭证引用</div>
                          <div class="mt-1 text-sm font-medium text-white">
                            {{ currentProject?.authRef || '-' }}
                          </div>
                        </div>
                      </div>

                      <div
                        class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                      >
                        <div class="flex items-center justify-between gap-3">
                          <div>
                            <div class="text-sm font-semibold text-white">
                              接口映射
                            </div>
                            <div class="mt-1 text-xs text-slate-400">
                              这些是原型约定，不是真实后端响应。
                            </div>
                          </div>
                          <StatusBadge
                            :status="
                              normalizeBadgeStatus(currentProject?.syncState)
                            "
                          />
                        </div>

                        <div class="mt-4 grid gap-3 md:grid-cols-2">
                          <div
                            v-for="contract in projectContracts"
                            :key="contract.path"
                            class="rounded-2xl border border-white/10 bg-white/5 p-3"
                          >
                            <div
                              class="flex items-center justify-between gap-2"
                            >
                              <span
                                class="rounded-full bg-cyan-400/15 px-2 py-1 text-[11px] font-semibold text-cyan-200"
                              >
                                {{ contract.method }}
                              </span>
                              <span
                                class="font-mono text-[11px] text-slate-300"
                              >
                                {{ contract.path }}
                              </span>
                            </div>
                            <div class="mt-2 text-xs leading-5 text-slate-400">
                              {{ contract.purpose }}
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </BaseCard>

                  <BaseCard
                    padding="none"
                    class="overflow-hidden border border-white/10 bg-white/4 shadow-none"
                  >
                    <template #header>
                      <div class="flex items-center justify-between gap-3">
                        <div>
                          <h3 class="text-sm font-semibold text-white">
                            数据源详情
                          </h3>
                          <p class="mt-1 text-xs text-slate-400">
                            同步任务实例属于这里，而不是独立悬空页面。
                          </p>
                        </div>
                        <BaseButton
                          v-if="activeRole === 'admin'"
                          variant="outline"
                          size="sm"
                          @click="triggerManualSync(currentProject)"
                        >
                          手动同步
                        </BaseButton>
                      </div>
                    </template>

                    <div class="space-y-4 p-4">
                      <div
                        class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                      >
                        <div class="flex items-center justify-between gap-3">
                          <div>
                            <div class="text-sm font-semibold text-white">
                              {{ currentProject?.name || '无项目' }}
                            </div>
                            <div class="mt-1 text-xs text-slate-400">
                              {{ currentProject?.description || '暂无描述' }}
                            </div>
                          </div>
                          <StatusBadge
                            :status="
                              normalizeBadgeStatus(currentProject?.syncState)
                            "
                          />
                        </div>

                        <div class="mt-4 grid gap-2 text-xs text-slate-300">
                          <div class="flex items-center justify-between gap-3">
                            <span class="text-slate-500">最近同步</span>
                            <span>{{
                              formatClock(currentProject?.lastSyncedAt)
                            }}</span>
                          </div>
                          <div class="flex items-start justify-between gap-3">
                            <span class="text-slate-500">最近错误</span>
                            <span
                              class="max-w-[18rem] text-right text-rose-200"
                            >
                              {{ currentProject?.lastSyncError || '无' }}
                            </span>
                          </div>
                          <div class="flex items-center justify-between gap-3">
                            <span class="text-slate-500">权限</span>
                            <span>{{
                              currentProject?.permissions?.join(' / ') || '-'
                            }}</span>
                          </div>
                        </div>
                      </div>

                      <div
                        class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                      >
                        <div class="flex items-center justify-between gap-3">
                          <div>
                            <div class="text-sm font-semibold text-white">
                              同步任务实例
                            </div>
                            <div class="mt-1 text-xs text-slate-400">
                              展示每一次任务实例的状态、触发方式与错误码。
                            </div>
                          </div>
                          <span
                            class="rounded-full border border-white/10 px-2.5 py-1 text-[11px] text-slate-400"
                          >
                            {{ currentProject?.syncHistory?.length || 0 }} 条
                          </span>
                        </div>

                        <div
                          v-if="currentProject?.syncHistory?.length"
                          class="mt-4 space-y-3"
                        >
                          <div
                            v-for="task in currentProject.syncHistory"
                            :key="task.id"
                            class="rounded-2xl border border-white/10 bg-white/5 p-3"
                          >
                            <div class="flex items-start justify-between gap-3">
                              <div>
                                <div class="text-sm font-medium text-white">
                                  {{ task.id }}
                                </div>
                                <div class="mt-1 text-xs text-slate-400">
                                  {{ task.trigger }} ·
                                  {{ formatLongClock(task.startedAt) }}
                                </div>
                              </div>
                              <StatusBadge
                                :status="normalizeBadgeStatus(task.status)"
                              />
                            </div>

                            <div
                              v-if="task.status === 'processing'"
                              class="mt-3"
                            >
                              <div
                                class="flex items-center justify-between text-xs text-slate-400"
                              >
                                <span>进度</span>
                                <span>{{ task.progress || 0 }}%</span>
                              </div>
                              <div
                                class="mt-2 h-2 overflow-hidden rounded-full bg-white/10"
                              >
                                <div
                                  class="h-full rounded-full bg-cyan-400 transition-all"
                                  :style="{ width: `${task.progress || 0}%` }"
                                />
                              </div>
                            </div>

                            <div class="mt-3 text-xs leading-5 text-slate-300">
                              {{ task.message || '暂无任务说明' }}
                            </div>

                            <div
                              class="mt-2 flex flex-wrap items-center gap-3 text-[11px] text-slate-500"
                            >
                              <span
                                >结束时间：{{
                                  formatLongClock(task.finishedAt)
                                }}</span
                              >
                              <span v-if="task.errorCode"
                                >错误码：{{ task.errorCode }}</span
                              >
                            </div>
                          </div>
                        </div>

                        <div
                          v-else
                          class="mt-4 rounded-3xl border border-dashed border-white/15 bg-white/4 px-4 py-10 text-center"
                        >
                          <div class="text-sm font-medium text-white">
                            暂无同步任务实例
                          </div>
                          <div class="mt-1 text-xs leading-5 text-slate-400">
                            这是同步记录的空态，不需要单独建一个空白页面。
                          </div>
                        </div>
                      </div>
                    </div>
                  </BaseCard>
                </div>
              </section>

              <section v-else-if="activeTab === 'query'" class="space-y-6">
                <div
                  class="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]"
                >
                  <BaseCard
                    padding="none"
                    class="overflow-hidden border border-white/10 bg-white/4 shadow-none"
                  >
                    <template #header>
                      <div class="flex items-center justify-between gap-3">
                        <div>
                          <h3 class="text-sm font-semibold text-white">
                            查询提交
                          </h3>
                          <p class="mt-1 text-xs text-slate-400">
                            通过一个模拟 SSE
                            流程展示加载、失败、取消与部分答案。
                          </p>
                        </div>
                        <StatusBadge
                          :status="normalizeBadgeStatus(query.status)"
                        />
                      </div>
                    </template>

                    <div class="space-y-4 p-4">
                      <div
                        v-if="activeRole === 'user'"
                        class="rounded-3xl border border-emerald-400/30 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-100"
                      >
                        普通用户可以直接提问；模型与项目选择保持只读默认值。
                      </div>

                      <div class="grid gap-4 md:grid-cols-2">
                        <label class="space-y-2 text-sm text-slate-300">
                          <span
                            class="text-xs uppercase tracking-[0.2em] text-slate-500"
                          >
                            目标数据源
                          </span>
                          <select v-model="query.projectId" class="input">
                            <option
                              v-for="project in projects"
                              :key="project.id"
                              :value="project.id"
                            >
                              {{ project.name }}
                            </option>
                          </select>
                        </label>

                        <label class="space-y-2 text-sm text-slate-300">
                          <span
                            class="text-xs uppercase tracking-[0.2em] text-slate-500"
                          >
                            模型
                          </span>
                          <select v-model="query.model" class="input">
                            <option
                              v-for="model in modelOptions"
                              :key="model"
                              :value="model"
                            >
                              {{ model }}
                            </option>
                          </select>
                        </label>
                      </div>

                      <div class="grid gap-4 md:grid-cols-3">
                        <button
                          v-for="outcome in queryOutcomes"
                          :key="outcome.key"
                          class="rounded-2xl border px-4 py-3 text-left transition"
                          :class="
                            query.outcome === outcome.key
                              ? 'border-cyan-400/50 bg-cyan-400/10'
                              : 'border-white/10 bg-white/5 hover:bg-white/10'
                          "
                          @click="query.outcome = outcome.key"
                        >
                          <div class="text-sm font-medium text-white">
                            {{ outcome.label }}
                          </div>
                          <div class="mt-1 text-xs leading-5 text-slate-400">
                            {{ outcome.hint }}
                          </div>
                        </button>
                      </div>

                      <label class="space-y-2 text-sm text-slate-300">
                        <span
                          class="text-xs uppercase tracking-[0.2em] text-slate-500"
                        >
                          问题
                        </span>
                        <textarea
                          v-model="query.question"
                          rows="6"
                          class="input resize-none"
                          placeholder="输入一个想要提问的问题"
                        />
                      </label>

                      <div class="flex flex-wrap gap-2">
                        <BaseButton
                          variant="primary"
                          :loading="
                            query.status === 'queued' ||
                            query.status === 'streaming'
                          "
                          @click="startQuery"
                        >
                          提交查询
                        </BaseButton>
                        <BaseButton
                          variant="secondary"
                          :disabled="!canCancelQuery"
                          @click="cancelQuery"
                        >
                          中止
                        </BaseButton>
                        <BaseButton variant="outline" @click="resetQuery">
                          清空
                        </BaseButton>
                      </div>

                      <div class="grid gap-2 sm:grid-cols-3">
                        <div
                          v-for="preset in questionPresets"
                          :key="preset"
                          class="rounded-2xl border border-white/10 bg-white/5 px-3 py-3 text-xs leading-5 text-slate-300"
                        >
                          {{ preset }}
                        </div>
                      </div>
                    </div>
                  </BaseCard>

                  <BaseCard
                    padding="none"
                    class="overflow-hidden border border-white/10 bg-white/4 shadow-none"
                  >
                    <template #header>
                      <div class="flex items-center justify-between gap-3">
                        <div>
                          <h3 class="text-sm font-semibold text-white">
                            SSE 流式展示
                          </h3>
                          <p class="mt-1 text-xs text-slate-400">
                            用事件时间线模拟从排队到答案落地的全过程。
                          </p>
                        </div>
                        <span
                          class="rounded-full border border-white/10 px-2.5 py-1 text-[11px] text-slate-400"
                        >
                          {{ query.phase }}
                        </span>
                      </div>
                    </template>

                    <div class="space-y-4 p-4">
                      <div
                        class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                      >
                        <div class="flex items-center justify-between gap-3">
                          <div>
                            <div class="text-sm font-semibold text-white">
                              当前状态
                            </div>
                            <div class="mt-1 text-xs text-slate-400">
                              {{ queryStatusMessage }}
                            </div>
                          </div>
                          <StatusBadge
                            :status="normalizeBadgeStatus(query.status)"
                          />
                        </div>

                        <div
                          class="mt-4 h-2 overflow-hidden rounded-full bg-white/10"
                        >
                          <div
                            class="h-full rounded-full bg-gradient-to-r from-cyan-400 via-sky-400 to-emerald-400 transition-all duration-300"
                            :style="{ width: `${query.progress}%` }"
                          />
                        </div>
                        <div
                          class="mt-2 flex items-center justify-between text-[11px] text-slate-500"
                        >
                          <span>{{ query.progress }}%</span>
                          <span>{{ query.modeLabel }}</span>
                        </div>
                      </div>

                      <BaseLoading
                        v-if="
                          query.status === 'queued' ||
                          query.status === 'streaming'
                        "
                        text="SSE 正在持续输出中"
                        variant="primary"
                      />

                      <div class="space-y-2">
                        <div
                          class="text-xs uppercase tracking-[0.2em] text-slate-500"
                        >
                          事件时间线
                        </div>
                        <div v-if="query.events.length" class="space-y-2">
                          <div
                            v-for="event in query.events"
                            :key="event.id"
                            class="rounded-2xl border border-white/10 bg-white/5 p-3"
                          >
                            <div
                              class="flex items-center justify-between gap-3"
                            >
                              <div class="flex items-center gap-2">
                                <span
                                  class="h-2.5 w-2.5 rounded-full"
                                  :class="eventDotClass(event.type)"
                                />
                                <span class="text-sm font-medium text-white">
                                  {{ event.title }}
                                </span>
                              </div>
                              <span class="text-[11px] text-slate-500">
                                {{ event.time }}
                              </span>
                            </div>
                            <div class="mt-2 text-xs leading-5 text-slate-400">
                              {{ event.detail }}
                            </div>
                          </div>
                        </div>

                        <div
                          v-else
                          class="rounded-3xl border border-dashed border-white/15 bg-white/4 px-4 py-10 text-center"
                        >
                          <div class="text-sm font-medium text-white">
                            暂无流式事件
                          </div>
                          <div class="mt-1 text-xs leading-5 text-slate-400">
                            点击“提交查询”即可生成 SSE 事件序列。
                          </div>
                        </div>
                      </div>

                      <div class="grid gap-3 lg:grid-cols-2">
                        <div
                          class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                        >
                          <div class="flex items-center justify-between gap-3">
                            <div>
                              <div class="text-sm font-semibold text-white">
                                部分答案
                              </div>
                              <div class="mt-1 text-xs text-slate-400">
                                失败时保留中间结果，避免“点了没反应”。
                              </div>
                            </div>
                            <StatusBadge
                              :status="
                                query.partialAnswer ? 'processing' : 'disabled'
                              "
                            />
                          </div>
                          <div
                            class="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-200"
                          >
                            {{ query.partialAnswer || '等待生成部分答案……' }}
                          </div>
                        </div>

                        <div
                          class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                        >
                          <div class="flex items-center justify-between gap-3">
                            <div>
                              <div class="text-sm font-semibold text-white">
                                最终答案
                              </div>
                              <div class="mt-1 text-xs text-slate-400">
                                成功态时写入完整回答。
                              </div>
                            </div>
                            <StatusBadge
                              :status="
                                query.finalAnswer
                                  ? 'success'
                                  : query.status === 'failed'
                                    ? 'failed'
                                    : 'pending'
                              "
                            />
                          </div>
                          <div
                            class="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-200"
                          >
                            {{ query.finalAnswer || queryErrorMessage }}
                          </div>
                        </div>
                      </div>
                    </div>
                  </BaseCard>
                </div>
              </section>

              <section v-else class="space-y-6">
                <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
                  <BaseCard
                    padding="none"
                    class="overflow-hidden border border-white/10 bg-white/4 shadow-none"
                  >
                    <template #header>
                      <div class="flex items-center justify-between gap-3">
                        <div>
                          <h3 class="text-sm font-semibold text-white">
                            系统健康
                          </h3>
                          <p class="mt-1 text-xs text-slate-400">
                            这里展示调度、容量、全局配置和健康状态。
                          </p>
                        </div>
                        <StatusBadge :status="currentSystemBadge" />
                      </div>
                    </template>

                    <div class="space-y-4 p-4">
                      <div class="grid gap-3 md:grid-cols-4">
                        <div
                          v-for="card in systemMetrics"
                          :key="card.label"
                          class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                        >
                          <div class="text-xs text-slate-500">
                            {{ card.label }}
                          </div>
                          <div class="mt-2 text-2xl font-semibold text-white">
                            {{ card.value }}
                          </div>
                          <div class="mt-1 text-xs text-slate-400">
                            {{ card.help }}
                          </div>
                        </div>
                      </div>

                      <div class="grid gap-4 lg:grid-cols-2">
                        <div
                          class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                        >
                          <div class="flex items-center justify-between gap-3">
                            <div>
                              <div class="text-sm font-semibold text-white">
                                全局配置
                              </div>
                              <div class="mt-1 text-xs text-slate-400">
                                只展示原型里最关键的系统约束。
                              </div>
                            </div>
                            <span
                              class="rounded-full border border-white/10 px-2.5 py-1 text-[11px] text-slate-400"
                            >
                              只读
                            </span>
                          </div>

                          <div class="mt-4 space-y-2">
                            <div
                              class="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-3"
                            >
                              <span class="text-sm text-slate-300"
                                >单次调用超时</span
                              >
                              <span class="font-medium text-white">120 秒</span>
                            </div>
                            <div
                              class="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-3"
                            >
                              <span class="text-sm text-slate-300"
                                >并发容器上限</span
                              >
                              <span class="font-medium text-white">6</span>
                            </div>
                            <div
                              class="flex items-center justify-between gap-3 rounded-2xl border border-white/10 bg-white/5 px-3 py-3"
                            >
                              <span class="text-sm text-slate-300"
                                >资源限制</span
                              >
                              <span class="font-medium text-white"
                                >CPU 0.5 / Memory 512m</span
                              >
                            </div>
                          </div>
                        </div>

                        <div
                          class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                        >
                          <div class="flex items-center justify-between gap-3">
                            <div>
                              <div class="text-sm font-semibold text-white">
                                调度任务
                              </div>
                              <div class="mt-1 text-xs text-slate-400">
                                展示 last_status 与
                                last_run，不另开独立调度页面。
                              </div>
                            </div>
                          </div>

                          <div class="mt-4 space-y-3">
                            <div
                              v-for="task in scheduledTasks"
                              :key="task.name"
                              class="rounded-2xl border border-white/10 bg-white/5 p-3"
                            >
                              <div
                                class="flex items-start justify-between gap-3"
                              >
                                <div>
                                  <div class="text-sm font-medium text-white">
                                    {{ task.name }}
                                  </div>
                                  <div class="mt-1 text-xs text-slate-400">
                                    {{ task.note }}
                                  </div>
                                </div>
                                <StatusBadge
                                  :status="
                                    normalizeBadgeStatus(task.lastStatus)
                                  "
                                />
                              </div>
                              <div
                                class="mt-3 grid gap-2 text-xs text-slate-400"
                              >
                                <div
                                  class="flex items-center justify-between gap-3"
                                >
                                  <span>Schedule</span>
                                  <span class="font-mono text-slate-300">
                                    {{ task.schedule }}
                                  </span>
                                </div>
                                <div
                                  class="flex items-center justify-between gap-3"
                                >
                                  <span>Last run</span>
                                  <span class="text-slate-300">
                                    {{ formatLongClock(task.lastRun) }}
                                  </span>
                                </div>
                                <div
                                  class="flex items-center justify-between gap-3"
                                >
                                  <span>Next run</span>
                                  <span class="text-slate-300">
                                    {{ formatLongClock(task.nextRun) }}
                                  </span>
                                </div>
                                <div
                                  v-if="task.lastError"
                                  class="rounded-2xl border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-rose-100"
                                >
                                  {{ task.lastError }}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </BaseCard>

                  <BaseCard
                    padding="none"
                    class="overflow-hidden border border-white/10 bg-white/4 shadow-none"
                  >
                    <template #header>
                      <div>
                        <h3 class="text-sm font-semibold text-white">
                          实时观察
                        </h3>
                        <p class="mt-1 text-xs text-slate-400">
                          这个侧栏帮助 board 快速确认当前状态，不是独立页面。
                        </p>
                      </div>
                    </template>

                    <div class="space-y-4 p-4">
                      <div
                        class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                      >
                        <div
                          class="text-xs uppercase tracking-[0.2em] text-slate-500"
                        >
                          当前角色
                        </div>
                        <div class="mt-2 text-lg font-semibold text-white">
                          {{ activeRoleLabel }}
                        </div>
                        <div class="mt-2 text-sm leading-6 text-slate-400">
                          管理员可以操作配置、删除和同步；普通用户只读。
                        </div>
                      </div>

                      <div
                        class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                      >
                        <div
                          class="text-xs uppercase tracking-[0.2em] text-slate-500"
                        >
                          当前项目
                        </div>
                        <div class="mt-2 text-lg font-semibold text-white">
                          {{ currentProject?.name || '无项目' }}
                        </div>
                        <div class="mt-2 text-sm leading-6 text-slate-400">
                          {{ currentProject?.sourceType || '-' }} ·
                          {{ currentProject?.syncState || '-' }}
                        </div>
                        <div class="mt-4">
                          <StatusBadge
                            :status="
                              normalizeBadgeStatus(currentProject?.syncState)
                            "
                          />
                        </div>
                      </div>

                      <div
                        class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
                      >
                        <div
                          class="text-xs uppercase tracking-[0.2em] text-slate-500"
                        >
                          注意事项
                        </div>
                        <ul
                          class="mt-3 space-y-2 text-sm leading-6 text-slate-300"
                        >
                          <li>
                            抽屉采用全高右侧面板，底部固定，不再出现“没到底”的问题。
                          </li>
                          <li>
                            同步任务实例属于数据源详情，不再作为悬空页面。
                          </li>
                          <li>
                            查询流保留部分答案和取消态，避免点了没有反馈。
                          </li>
                          <li>
                            所有示意数据均为 mock，不展示真实 Token 或凭证。
                          </li>
                        </ul>
                      </div>
                    </div>
                  </BaseCard>
                </div>
              </section>
            </div>
          </BaseCard>
        </main>

        <aside class="space-y-6">
          <BaseCard
            padding="none"
            class="overflow-hidden border border-white/10 bg-slate-900/80 shadow-none"
          >
            <template #header>
              <div>
                <h2 class="text-base font-semibold text-white">系统快照</h2>
                <p class="mt-1 text-xs text-slate-400">
                  这是给 board 快速扫一眼的实时摘要。
                </p>
              </div>
            </template>

            <div class="space-y-4 p-4">
              <div
                class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
              >
                <div class="flex items-center justify-between gap-3">
                  <div>
                    <div
                      class="text-xs uppercase tracking-[0.2em] text-slate-500"
                    >
                      系统状态
                    </div>
                    <div class="mt-2 text-2xl font-semibold text-white">
                      {{ systemSnapshot.title }}
                    </div>
                  </div>
                  <StatusBadge :status="currentSystemBadge" />
                </div>
                <div class="mt-3 text-sm leading-6 text-slate-400">
                  {{ systemSnapshot.description }}
                </div>
              </div>

              <div class="grid gap-3">
                <div
                  v-for="item in snapshotCards"
                  :key="item.label"
                  class="rounded-3xl border border-white/10 bg-white/5 p-4"
                >
                  <div class="text-xs text-slate-500">{{ item.label }}</div>
                  <div class="mt-2 text-lg font-semibold text-white">
                    {{ item.value }}
                  </div>
                  <div class="mt-1 text-xs text-slate-400">
                    {{ item.help }}
                  </div>
                </div>
              </div>

              <div
                class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
              >
                <div class="text-xs uppercase tracking-[0.2em] text-slate-500">
                  当前同步状态
                </div>
                <div class="mt-2 text-lg font-semibold text-white">
                  {{ currentProject?.name || '-' }}
                </div>
                <div
                  class="mt-3 flex items-center justify-between gap-3 text-sm"
                >
                  <span class="text-slate-400">最近同步</span>
                  <span class="text-slate-200">
                    {{ formatClock(currentProject?.lastSyncedAt) }}
                  </span>
                </div>
                <div
                  class="mt-2 flex items-center justify-between gap-3 text-sm"
                >
                  <span class="text-slate-400">状态</span>
                  <StatusBadge
                    :status="normalizeBadgeStatus(currentProject?.syncState)"
                  />
                </div>
              </div>

              <div
                class="rounded-3xl border border-white/10 bg-slate-950/70 p-4"
              >
                <div class="text-xs uppercase tracking-[0.2em] text-slate-500">
                  已知边界
                </div>
                <div class="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                  <div>• 右侧抽屉全高贴底，专门解决之前未到底的问题。</div>
                  <div>• 搜索为空会出现真实空态，而不是空白页面。</div>
                  <div>• 查询失败保留部分结果，不让状态“卡死”。</div>
                  <div>• 同步任务实例直接挂在数据源详情下。</div>
                </div>
              </div>
            </div>
          </BaseCard>

          <BaseCard
            padding="none"
            class="overflow-hidden border border-white/10 bg-slate-900/80 shadow-none"
          >
            <template #header>
              <div>
                <h2 class="text-base font-semibold text-white">可见性说明</h2>
                <p class="mt-1 text-xs text-slate-400">
                  方便 Developer 直接拆解实现的约束。
                </p>
              </div>
            </template>

            <div class="space-y-3 p-4 text-sm text-slate-300">
              <div class="rounded-2xl border border-white/10 bg-white/5 p-3">
                项目配置采用可编辑抽屉，管理员可保存，普通用户只读。
              </div>
              <div class="rounded-2xl border border-white/10 bg-white/5 p-3">
                查询支持开始、中止、重置，并在失败态保留部分答案。
              </div>
              <div class="rounded-2xl border border-white/10 bg-white/5 p-3">
                系统状态展示调度任务、并发容量、配置约束与健康情况。
              </div>
            </div>
          </BaseCard>
        </aside>
      </div>
    </div>

    <Teleport to="body">
      <Transition
        enter-active-class="transition duration-300 ease-out"
        enter-from-class="translate-x-full opacity-0"
        enter-to-class="translate-x-0 opacity-100"
        leave-active-class="transition duration-200 ease-in"
        leave-from-class="translate-x-0 opacity-100"
        leave-to-class="translate-x-full opacity-0"
      >
        <div v-if="drawerOpen" class="fixed inset-0 z-50">
          <div
            class="absolute inset-0 bg-slate-950/70 backdrop-blur-sm"
            @click="closeDrawer"
          />
          <div
            class="absolute inset-y-0 right-0 flex h-full w-full max-w-[560px] flex-col border-l border-white/10 bg-slate-950 shadow-2xl"
          >
            <div class="flex-shrink-0 border-b border-white/10 px-6 py-5">
              <div class="flex items-start justify-between gap-4">
                <div>
                  <div
                    class="text-xs uppercase tracking-[0.2em] text-slate-500"
                  >
                    {{ drawerMode === 'create' ? 'Create' : 'Edit' }}
                  </div>
                  <h3 class="mt-2 text-xl font-semibold text-white">
                    {{ drawerMode === 'create' ? '新建数据源' : '编辑数据源' }}
                  </h3>
                  <p class="mt-1 text-sm leading-6 text-slate-400">
                    抽屉固定到底部，作为全高右侧面板使用。
                  </p>
                </div>
                <button
                  class="rounded-full border border-white/10 bg-white/5 p-2 text-slate-300 transition hover:bg-white/10"
                  @click="closeDrawer"
                >
                  <svg
                    class="h-5 w-5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="2"
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>
            </div>

            <div class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
              <div class="space-y-4">
                <BaseInput
                  v-model="drawerDraft.name"
                  label="项目名称"
                  placeholder="请输入项目名称"
                  :error="drawerErrors.name"
                />

                <label class="space-y-2 text-sm text-slate-300">
                  <span
                    class="text-xs uppercase tracking-[0.2em] text-slate-500"
                    >来源类型</span
                  >
                  <select v-model="drawerDraft.sourceType" class="input">
                    <option>Git</option>
                    <option>飞书文档</option>
                    <option>本地目录</option>
                  </select>
                </label>

                <BaseInput
                  v-model="drawerDraft.sourceUrl"
                  label="来源地址"
                  placeholder="https://..."
                  :error="drawerErrors.sourceUrl"
                />

                <BaseInput
                  v-model="drawerDraft.authRef"
                  label="凭证引用"
                  placeholder="例如 git-token-ref-001"
                  help="只展示引用名，不展示真实密钥或 Token。"
                />

                <BaseInput
                  v-model="drawerDraft.localPath"
                  label="本地同步路径"
                  placeholder="/opt/sourcelens/project"
                  :error="drawerErrors.localPath"
                />

                <BaseInput
                  v-model="drawerDraft.refreshInterval"
                  label="刷新周期（分钟）"
                  type="number"
                  :error="drawerErrors.refreshInterval"
                />

                <label class="space-y-2 text-sm text-slate-300">
                  <span
                    class="text-xs uppercase tracking-[0.2em] text-slate-500"
                    >项目描述</span
                  >
                  <textarea
                    v-model="drawerDraft.description"
                    rows="6"
                    class="input resize-none"
                    placeholder="说明项目用途、同步边界和查询意图"
                  />
                </label>

                <div
                  v-if="drawerMode === 'edit' && activeRole === 'user'"
                  class="rounded-3xl border border-amber-400/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100"
                >
                  当前为普通用户视图，此抽屉仅展示字段，不允许保存。
                </div>
              </div>
            </div>

            <div
              class="flex-shrink-0 border-t border-white/10 bg-slate-950/95 px-6 py-4"
            >
              <div class="flex flex-wrap justify-end gap-2">
                <BaseButton variant="secondary" @click="closeDrawer">
                  取消
                </BaseButton>
                <BaseButton
                  variant="primary"
                  :disabled="activeRole === 'user'"
                  @click="saveDrawer"
                >
                  保存
                </BaseButton>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>

    <BaseModal
      :show="deleteModalOpen"
      title="删除数据源"
      icon-type="warning"
      @close="deleteModalOpen = false"
    >
      <div class="space-y-3 text-sm text-slate-700">
        <p>
          该操作会从 mock
          列表中移除当前数据源，继续前请确认它没有被其他流程依赖。
        </p>
        <p class="font-medium text-slate-900">
          {{ deleteTarget?.name || '未选择数据源' }}
        </p>
      </div>

      <template #footer>
        <div class="flex flex-wrap justify-end gap-2">
          <BaseButton variant="secondary" @click="deleteModalOpen = false">
            取消
          </BaseButton>
          <BaseButton variant="danger" @click="confirmDelete">
            确认删除
          </BaseButton>
        </div>
      </template>
    </BaseModal>

    <Toast />
  </div>
</template>

<script setup>
import { computed, reactive, ref, watch } from 'vue'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseCard from '@/components/ui/BaseCard.vue'
import BaseInput from '@/components/ui/BaseInput.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'
import Toast from '@/components/ui/Toast.vue'
import { useToast } from '@/composables/useToast'

import {
  apiContracts,
  clone,
  createProjectDraft,
  formatClock,
  formatLongClock,
  modelOptions,
  navTabs,
  normalizeBadgeStatus,
  projectSeed,
  queryOutcomes,
  questionPresets,
  scheduledTasks
} from './mock'

const { showSuccess, showError, showInfo, showWarning } = useToast()

const roleOptions = [
  { key: 'admin', label: '管理员' },
  { key: 'user', label: '普通用户' }
]

const projectContracts = [
  {
    method: 'GET',
    path: '/api/v1/projects/:id',
    purpose: '读取单个项目与同步历史'
  },
  {
    method: 'POST',
    path: '/api/v1/projects/:id/sync',
    purpose: '发起一次同步任务实例'
  },
  {
    method: 'POST',
    path: '/api/v1/projects',
    purpose: '新增一个项目配置'
  },
  {
    method: 'PATCH',
    path: '/api/v1/projects/:id',
    purpose: '更新项目配置'
  }
]

const projects = ref(clone(projectSeed))
const activeProjectId = ref(projects.value[0]?.id || '')
const activeRole = ref('admin')
const activeTab = ref('projects')
const projectSearch = ref('')
const drawerOpen = ref(false)
const drawerMode = ref('create')
const drawerDraft = reactive(createProjectDraft())
const drawerErrors = reactive({})
const deleteModalOpen = ref(false)
const deleteTarget = ref(null)

const query = reactive({
  projectId: projects.value[0]?.id || '',
  model: modelOptions[0],
  outcome: 'success',
  question: '请解释为什么同步任务应该归属于数据源管理。',
  status: 'idle',
  phase: '等待提交',
  progress: 0,
  events: [],
  partialAnswer: '',
  finalAnswer: '',
  error: '',
  modeLabel: '正常流式'
})

const queryTimers = new Set()
const syncTimers = new Set()

const roleLabelMap = {
  admin: '管理员',
  user: '普通用户'
}

const outcomeModeLabel = {
  success: '正常流式',
  partial: '部分答案保留',
  timeout: '超时失败'
}

const currentProject = computed(
  () =>
    projects.value.find((project) => project.id === activeProjectId.value) ||
    projects.value[0] ||
    null
)

const visibleProjects = computed(() => {
  const term = projectSearch.value.trim().toLowerCase()
  if (!term) {
    return projects.value
  }
  return projects.value.filter((project) => {
    const haystack = [
      project.name,
      project.sourceType,
      project.localPath,
      project.description,
      project.sourceUrl
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(term)
  })
})

const activeTabLabel = computed(() => {
  return navTabs.find((tab) => tab.key === activeTab.value)?.label || '项目配置'
})

const activeTabHint = computed(() => {
  return navTabs.find((tab) => tab.key === activeTab.value)?.hint || ''
})

const activeRoleLabel = computed(
  () => roleLabelMap[activeRole.value] || '普通用户'
)

const queryStatusMessage = computed(() => {
  if (query.status === 'queued') {
    return '请求已进入队列，等待容器资源。'
  }
  if (query.status === 'streaming') {
    return 'SSE 正在持续输出，界面保持可见反馈。'
  }
  if (query.status === 'failed') {
    return '请求失败，但已尽量保留部分答案。'
  }
  if (query.status === 'cancelled') {
    return '用户已取消，当前片段仍然保留。'
  }
  if (query.status === 'success') {
    return '本次查询已完成，最终答案已经落地。'
  }
  return '等待提交问题。'
})

const queryErrorMessage = computed(() => {
  if (query.error) {
    if (query.error === 'LENS_SANDBOX_TIMEOUT') {
      return '沙箱执行超时，页面已保留部分答案。'
    }
    if (query.error === 'LENS_ENGINE_NOT_IMPLEMENTED') {
      return '引擎路径尚未完整实现，已保留可读片段。'
    }
    return query.error
  }
  if (query.status === 'cancelled') {
    return '取消中保留了部分答案，用户可再次提交。'
  }
  return '最终答案会在成功态显示；失败时这里展示错误或保留说明。'
})

const canCancelQuery = computed(
  () => query.status === 'queued' || query.status === 'streaming'
)

const currentSystemBadge = computed(() => {
  if (query.status === 'failed') {
    return 'failed'
  }
  if (currentProject.value?.syncState === 'failed') {
    return 'failed'
  }
  if (query.status === 'streaming' || query.status === 'queued') {
    return 'processing'
  }
  if (currentProject.value?.syncState === 'disabled') {
    return 'disabled'
  }
  return 'success'
})

const topMetrics = computed(() => [
  {
    label: '数据源总数',
    value: `${projects.value.length}`,
    help: '包含项目配置和同步历史'
  },
  {
    label: '可编辑视图',
    value: activeRoleLabel.value,
    help: '决定按钮和抽屉是否可保存'
  },
  {
    label: '当前查询',
    value: query.status === 'idle' ? '待提交' : query.phase,
    help: 'SSE / 取消 / 部分答案'
  },
  {
    label: '系统健康',
    value: systemSnapshot.value.title,
    help: '调度、队列和缓存状态'
  }
])

const systemSnapshot = computed(() => {
  if (query.status === 'failed') {
    return {
      title: '轻度降级',
      description: '查询流出现失败，但页面保留了部分结果和错误信息。'
    }
  }
  if (query.status === 'streaming' || query.status === 'queued') {
    return {
      title: '处理中',
      description: '系统正在处理流式查询，右侧状态面板会持续刷新。'
    }
  }
  if (currentProject.value?.syncState === 'failed') {
    return {
      title: '同步异常',
      description: '某个数据源处于失败态，适合作为错误态演示。'
    }
  }
  if (currentProject.value?.syncState === 'disabled') {
    return {
      title: '只读',
      description: '当前项目没有持续同步，不需要独立同步任务页面。'
    }
  }
  return {
    title: '健康',
    description: '系统运行正常，SSE 与同步任务实例都能被正确展示。'
  }
})

const systemMetrics = computed(() => [
  {
    label: '并发上限',
    value: '6',
    help: '同时运行的容器数'
  },
  {
    label: '当前队列',
    value: query.status === 'queued' ? '1' : '0',
    help: '排队中的请求'
  },
  {
    label: '活跃容器',
    value: query.status === 'streaming' ? '1' : '0',
    help: '正在检索的临时容器'
  },
  {
    label: '最近同步',
    value: formatClock(currentProject.value?.lastSyncedAt),
    help: '当前选中数据源的最后一次同步'
  }
])

const snapshotCards = computed(() => [
  {
    label: '查询态',
    value: query.status === 'idle' ? '待提交' : query.phase,
    help: '包括加载、成功、失败与取消'
  },
  {
    label: '数据源态',
    value: currentProject.value?.syncState || '-',
    help: '同步实例属于数据源详情'
  },
  {
    label: '可见性',
    value: activeRoleLabel.value,
    help: '管理员与普通用户差异'
  }
])

function setDrawerErrors(errors = {}) {
  Object.keys(drawerErrors).forEach((key) => {
    delete drawerErrors[key]
  })
  Object.entries(errors).forEach(([key, value]) => {
    drawerErrors[key] = value
  })
}

function openDrawer(mode, project = null) {
  drawerMode.value = mode
  Object.assign(drawerDraft, createProjectDraft(project))
  setDrawerErrors()
  drawerOpen.value = true
}

function closeDrawer() {
  drawerOpen.value = false
}

function validateDrawer() {
  const errors = {}

  if (!drawerDraft.name.trim()) {
    errors.name = '项目名称不能为空'
  }
  if (!drawerDraft.sourceUrl.trim()) {
    errors.sourceUrl = '来源地址不能为空'
  } else if (!/^https?:\/\//i.test(drawerDraft.sourceUrl)) {
    errors.sourceUrl = '请输入有效的 URL'
  }
  if (!drawerDraft.localPath.trim()) {
    errors.localPath = '本地同步路径不能为空'
  }
  const interval = Number(drawerDraft.refreshInterval)
  if (Number.isNaN(interval) || interval <= 0) {
    errors.refreshInterval = '刷新周期必须大于 0'
  } else if (interval > 1440) {
    errors.refreshInterval = '刷新周期过大，请控制在 1440 分钟以内'
  }

  setDrawerErrors(errors)
  return Object.keys(errors).length === 0
}

function saveDrawer() {
  if (activeRole.value !== 'admin') {
    showWarning('普通用户只能查看配置，不能保存。')
    return
  }
  if (!validateDrawer()) {
    showError('请先修正右侧抽屉里的校验错误。')
    return
  }

  const nextProject = {
    id: drawerDraft.id,
    name: drawerDraft.name.trim(),
    sourceType: drawerDraft.sourceType,
    sourceUrl: drawerDraft.sourceUrl.trim(),
    authRef: drawerDraft.authRef.trim() || 'mock-token-ref',
    localPath: drawerDraft.localPath.trim(),
    refreshInterval: Number(drawerDraft.refreshInterval),
    description: drawerDraft.description.trim() || '暂无描述',
    syncState:
      drawerMode.value === 'create'
        ? 'pending'
        : currentProject.value?.syncState || 'pending',
    syncPolicy: currentProject.value?.syncPolicy || 'success',
    lastSyncedAt:
      drawerMode.value === 'create'
        ? null
        : currentProject.value?.lastSyncedAt || null,
    lastSyncError:
      drawerMode.value === 'create'
        ? ''
        : currentProject.value?.lastSyncError || '',
    owner: currentProject.value?.owner || '管理员',
    permissions: currentProject.value?.permissions || [
      '查询',
      '编辑',
      '手动同步'
    ],
    syncHistory:
      drawerMode.value === 'create'
        ? []
        : clone(currentProject.value?.syncHistory || [])
  }

  if (drawerMode.value === 'create') {
    projects.value = [nextProject, ...projects.value]
    activeProjectId.value = nextProject.id
  } else {
    projects.value = projects.value.map((project) =>
      project.id === nextProject.id ? nextProject : project
    )
  }

  closeDrawer()
  showSuccess(
    drawerMode.value === 'create' ? '已新建数据源配置' : '已保存数据源配置'
  )
}

function askDelete(project) {
  if (activeRole.value !== 'admin') {
    showWarning('普通用户没有删除权限。')
    return
  }
  deleteTarget.value = project
  deleteModalOpen.value = true
}

function confirmDelete() {
  if (!deleteTarget.value) {
    deleteModalOpen.value = false
    return
  }

  projects.value = projects.value.filter(
    (project) => project.id !== deleteTarget.value.id
  )
  activeProjectId.value = projects.value[0]?.id || ''
  deleteModalOpen.value = false
  showInfo(`已删除 ${deleteTarget.value.name}`)
  deleteTarget.value = null
}

function updateProject(projectId, updater) {
  projects.value = projects.value.map((project) => {
    if (project.id !== projectId) {
      return project
    }
    const next = clone(project)
    updater(next)
    return next
  })
}

function schedule(bucket, callback, delay) {
  const id = window.setTimeout(() => {
    bucket.delete(id)
    callback()
  }, delay)
  bucket.add(id)
  return id
}

function clearBucket(bucket) {
  bucket.forEach((id) => window.clearTimeout(id))
  bucket.clear()
}

function pushQueryEvent(type, title, detail) {
  query.events = [
    {
      id: `evt-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      type,
      title,
      detail,
      time: new Intl.DateTimeFormat('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      }).format(new Date())
    },
    ...query.events
  ].slice(0, 8)
}

function resetQuery() {
  clearBucket(queryTimers)
  query.status = 'idle'
  query.phase = '等待提交'
  query.progress = 0
  query.events = []
  query.partialAnswer = ''
  query.finalAnswer = ''
  query.error = ''
  query.modeLabel = outcomeModeLabel[query.outcome]
}

function startQuery() {
  clearBucket(queryTimers)
  query.status = 'queued'
  query.phase = '排队中'
  query.progress = 6
  query.events = []
  query.partialAnswer = ''
  query.finalAnswer = ''
  query.error = ''
  query.modeLabel = outcomeModeLabel[query.outcome]

  showInfo('查询已提交，开始模拟 SSE 流式反馈。')
  pushQueryEvent('queued', '请求进入队列', '等待沙箱容器与 Agent 资源释放。')

  schedule(
    queryTimers,
    () => {
      query.status = 'streaming'
      query.phase = '问题预处理'
      query.progress = 18
      pushQueryEvent(
        'preprocess',
        '问题预处理',
        '将用户问题整理成更适合检索的表达。'
      )
    },
    700
  )

  schedule(
    queryTimers,
    () => {
      if (query.status === 'cancelled') {
        return
      }
      query.phase = '沙箱启动'
      query.progress = 36
      pushQueryEvent('sandbox', '沙箱启动', '启动临时容器并挂载只读路径。')
    },
    1500
  )

  schedule(
    queryTimers,
    () => {
      if (query.status === 'cancelled') {
        return
      }
      query.phase = '检索阶段'
      query.progress = 54
      query.partialAnswer =
        'Agent 已经找到项目配置和同步记录，正在整理结果片段。'
      pushQueryEvent(
        'retrieve',
        'Agent 检索',
        '检索到了数据源配置、同步任务实例和查询相关字段。'
      )
    },
    2500
  )

  schedule(
    queryTimers,
    () => {
      if (query.status === 'cancelled') {
        return
      }
      query.phase = '结果整理'
      query.progress = 78
      pushQueryEvent(
        'summarize',
        '结果整理',
        'LLM 正在把原始检索结果变成可读答案。'
      )

      if (query.outcome === 'timeout') {
        query.status = 'failed'
        query.progress = 82
        query.error = 'LENS_SANDBOX_TIMEOUT'
        query.partialAnswer =
          '沙箱执行超时，但已保留部分查询片段，建议缩短范围或提升超时上限。'
        pushQueryEvent('error', '流式失败', '沙箱超时，已保留部分答案。')
        showError('SSE 流式失败：LENS_SANDBOX_TIMEOUT')
        return
      }
    },
    3600
  )

  schedule(
    queryTimers,
    () => {
      if (query.status === 'cancelled') {
        return
      }
      if (query.outcome === 'partial') {
        query.status = 'failed'
        query.progress = 88
        query.error = 'LENS_ENGINE_NOT_IMPLEMENTED'
        query.partialAnswer =
          '已生成部分答案：同步任务应并入数据源详情；右侧抽屉应贴底；普通用户只能只读。'
        pushQueryEvent(
          'error',
          '部分答案保留',
          '引擎未实现完整路径，但结果已被保留。'
        )
        showWarning('查询结束于失败态，但保留了部分答案。')
        return
      }

      query.status = 'success'
      query.phase = '完成'
      query.progress = 100
      query.finalAnswer =
        '最终答案：同步任务实例应展示在数据源详情内部；项目配置与查询流应通过可运行的 Vue + Tailwind 原型表达；失败态需保留部分答案。'
      pushQueryEvent('done', '流式完成', '完整回答已落地。')
      showSuccess('查询完成，最终答案已生成。')
    },
    4700
  )
}

function cancelQuery() {
  if (!canCancelQuery.value) {
    showInfo('当前没有可中止的查询。')
    return
  }

  clearBucket(queryTimers)
  query.status = 'cancelled'
  query.phase = '取消中'
  query.progress = Math.max(query.progress, 52)
  query.error = '用户主动取消'
  query.partialAnswer =
    query.partialAnswer || '查询已取消，但部分输出已经保留。'
  pushQueryEvent('cancel', '取消流式请求', '用户手动中止，保留当前片段。')
  showWarning('流式查询已取消，部分答案保留。')
}

function fillQuestion(text) {
  query.question = text
}

function triggerManualSync(project) {
  if (activeRole.value !== 'admin') {
    showWarning('普通用户不能手动触发同步。')
    return
  }
  if (!project || project.syncState === 'disabled') {
    showInfo('该数据源处于停用态，不需要手动同步。')
    return
  }

  const taskId = `sync-${Date.now()}`
  updateProject(project.id, (draft) => {
    draft.syncState = 'processing'
    draft.syncHistory = [
      {
        id: taskId,
        trigger: '手动',
        status: 'processing',
        startedAt: new Date().toISOString(),
        finishedAt: null,
        progress: 8,
        message: '手动同步已启动'
      },
      ...draft.syncHistory
    ]
  })

  showInfo(`已启动 ${project.name} 的同步任务实例。`)

  schedule(
    syncTimers,
    () => {
      updateProject(project.id, (draft) => {
        const current = draft.syncHistory.find((task) => task.id === taskId)
        if (current) {
          current.progress = 56
          current.message = '正在拉取增量内容'
        }
      })
    },
    700
  )

  schedule(
    syncTimers,
    () => {
      updateProject(project.id, (draft) => {
        const current = draft.syncHistory.find((task) => task.id === taskId)
        if (!current) {
          return
        }

        const success = draft.syncPolicy !== 'failed'
        current.status = success ? 'success' : 'failed'
        current.progress = 100
        current.finishedAt = new Date().toISOString()
        current.message = success ? '增量同步完成' : '同步失败：凭证或网络异常'
        current.errorCode = success ? '' : 'NETWORK_TIMEOUT'
        draft.syncState = success ? 'success' : 'failed'
        draft.lastSyncedAt = success ? current.finishedAt : draft.lastSyncedAt
        draft.lastSyncError = success ? '' : '凭证已失效：请更新引用后再试'
      })

      showSuccess(
        project.syncPolicy !== 'failed'
          ? `已完成 ${project.name} 的同步任务。`
          : `同步失败：${project.name} 需要更新凭证。`
      )
    },
    1800
  )
}

watch(
  activeProjectId,
  (value) => {
    query.projectId = value
  },
  { immediate: true }
)

watch(
  () => query.outcome,
  (value) => {
    query.modeLabel = outcomeModeLabel[value]
  },
  { immediate: true }
)

watch(
  projects,
  (items) => {
    if (
      items.length &&
      !items.some((item) => item.id === activeProjectId.value)
    ) {
      activeProjectId.value = items[0].id
    }
  },
  { deep: true }
)
</script>
