<template>
  <AdminLayout>
    <div class="mx-auto flex max-w-full flex-col gap-4 px-4 py-4 lg:px-6">
      <section class="overflow-hidden rounded-lg border border-line bg-surface shadow-sm">
        <div class="flex flex-col gap-4 border-b border-line px-5 py-4 lg:flex-row lg:items-start lg:justify-between">
          <div class="min-w-0 space-y-2">
            <div class="flex flex-wrap items-center gap-2">
              <h1 class="text-xl font-semibold text-ink-900">
                {{ activeMeta.title }}
              </h1>
              <span class="rounded-md border border-line bg-surface-sunken px-2 py-1 text-xs font-medium text-ink-500">
                {{ activeMeta.label }}
              </span>
            </div>
            <p class="max-w-3xl text-sm leading-6 text-ink-500">
              {{ activeMeta.description }}
            </p>
            <div class="flex flex-wrap items-center gap-2 text-xs text-ink-500">
              <span class="rounded-md border border-line bg-surface-sunken px-2 py-1">
                {{ t('lensAdmin.total', {
                  label: activeMeta.label,
                  count: activeCount
                }) }}
              </span>
              <span
                v-if="activeTab !== 'settings'"
                class="rounded-md border border-line bg-surface-sunken px-2 py-1"
              >
                {{ activeMeta.action }}
              </span>
            </div>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <BaseButton
              variant="outline"
              size="sm"
              :loading="loading"
              @click="load"
            >
              {{ t('common.refresh') }}
            </BaseButton>
            <BaseButton
              v-if="canCreate"
              variant="primary"
              size="sm"
              @click="startCreate"
            >
              {{ activeMeta.action }}
            </BaseButton>
          </div>
        </div>

        <div class="px-5 py-4">
          <BaseLoading v-if="loading && activeCount === 0" />

          <template v-else-if="activeTab === 'settings'">
            <div class="overflow-hidden rounded-lg border border-line">
              <table class="min-w-full table-fixed divide-y divide-line">
                <colgroup>
                  <col class="w-[48%]" />
                  <col class="w-[52%]" />
                </colgroup>
                <thead class="bg-surface-sunken">
                  <tr>
                    <th class="table-head">
                      {{ t('lensAdmin.settings.sectionTitle') }}
                    </th>
                    <th class="table-head">
                      {{ t('lensAdmin.columns.value') }}
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-line bg-surface">
                  <tr
                    v-for="setting in settingDefinitions"
                    :key="setting.key"
                    class="align-top transition-colors hover:bg-line-soft"
                  >
                    <td class="table-cell">
                      <div class="text-sm font-semibold text-ink-900">
                        {{ setting.label }}
                      </div>
                      <p class="mt-1 text-sm leading-6 text-ink-500">
                        {{ setting.description }}
                      </p>
                      <p class="mt-1 font-mono text-xs text-ink-400">
                        {{ setting.key }}
                      </p>
                    </td>
                    <td class="table-cell">
                      <div class="flex w-full items-center justify-end gap-3">
                        <input
                          v-if="setting.type === 'number'"
                          v-model.number="settingsForm[setting.key]"
                          type="number"
                          min="1"
                          class="w-full max-w-40 rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                        />
                        <select
                          v-else-if="setting.type === 'model_ref'"
                          v-model="settingsForm[setting.key]"
                          class="min-w-0 w-full max-w-lg rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                        >
                          <option value="">
                            {{ t('lensAdmin.placeholders.noModel') }}
                          </option>
                          <option
                            v-for="config in llmConfigOptions"
                            :key="config.uuid"
                            :value="config.uuid"
                          >
                            {{ formatLLMConfigLabel(config) }}
                          </option>
                        </select>
                        <span class="w-16 text-sm text-ink-500">
                          {{ setting.unit }}
                        </span>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="mt-6 overflow-hidden rounded-lg border border-line">
              <div class="border-b border-line px-4 py-3">
                <h3 class="text-sm font-semibold text-ink-900">
                  {{ t('lensAdmin.tasks.title') }}
                </h3>
                <p class="mt-1 text-sm text-ink-500">
                  {{ t('lensAdmin.tasks.description') }}
                </p>
              </div>
              <table class="min-w-full divide-y divide-line">
                <thead class="bg-surface-sunken">
                  <tr>
                    <th class="table-head">
                      {{ t('lensAdmin.tasks.task') }}
                    </th>
                    <th class="table-head">
                      {{ t('lensAdmin.tasks.enabled') }}
                    </th>
                    <th class="table-head">
                      {{ t('lensAdmin.tasks.lastRun') }}
                    </th>
                    <th class="table-head">
                      {{ t('lensAdmin.tasks.lastStatus') }}
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-line bg-surface">
                  <tr
                    v-for="task in defaultScheduledTasks"
                    :key="task.task_type"
                    class="align-top transition-colors hover:bg-line-soft"
                  >
                    <td class="table-cell">
                      <div class="text-sm font-semibold text-ink-900">
                        {{ task.label }}
                      </div>
                      <p class="mt-1 text-sm leading-6 text-ink-500">
                        {{ task.description }}
                      </p>
                      <p class="mt-1 font-mono text-xs text-ink-400">
                        {{ task.task_type }}
                      </p>
                    </td>
                    <td class="table-cell">
                      <label class="inline-flex items-center gap-2">
                        <input
                          :checked="task.enabled"
                          :disabled="taskSaving[task.task_type]"
                          type="checkbox"
                          class="h-4 w-4 rounded border-line text-brand-600 focus:ring-brand-500"
                          @change="
                            updateScheduledTaskEnabled(
                              task.task_type,
                              $event.target.checked
                            )
                          "
                        />
                        <span class="text-sm text-ink-600">
                          {{ task.enabled ? t('common.status.enabled') : t('common.status.disabled') }}
                        </span>
                      </label>
                    </td>
                    <td class="table-cell text-sm text-ink-600">
                      {{ formatDateTime(task.last_run_at) }}
                    </td>
                    <td class="table-cell">
                      <StatusBadge :status="task.last_status || 'unknown'" />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div class="mt-4 flex items-center justify-end gap-3 border-t border-line pt-4">
              <BaseButton
                variant="secondary"
                size="sm"
                :disabled="saving"
                @click="resetSettingsForm"
              >
                {{ t('lensAdmin.settings.reset') }}
              </BaseButton>
              <BaseButton
                variant="primary"
                size="sm"
                :loading="saving"
                @click="saveSettings"
              >
                {{ t('lensAdmin.settings.saveChanges') }}
              </BaseButton>
            </div>
            <p v-if="formError" class="mt-2 text-sm text-danger-700">
              {{ formError }}
            </p>
          </template>

          <div
            v-else-if="activeCount === 0"
            class="rounded-lg border border-line bg-surface-sunken py-16 text-center"
          >
            <p class="text-sm font-medium text-ink-500">
              {{ t('common.noData') }}
            </p>
          </div>

          <div
            v-else-if="activeTab === 'datasources'"
            class="relative overflow-x-auto rounded-lg border border-line bg-surface"
          >
              <table class="min-w-full divide-y divide-line">
                <thead class="bg-surface-sunken">
                  <tr>
                    <th class="table-head">
                      {{ t('lensAdmin.columns.datasource') }}
                    </th>
                    <th class="table-head">
                      {{ t('lensAdmin.columns.repository') }}
                    </th>
                    <th class="table-head">
                      {{ t('lensAdmin.columns.branch') }}
                    </th>
                    <th class="table-head">
                      {{ t('lensAdmin.columns.lensnode') }}
                    </th>
                    <th class="table-head">
                      {{ t('lensAdmin.columns.targetPath') }}
                    </th>
                    <th class="table-head">
                      {{ t('lensAdmin.columns.sync') }}
                    </th>
                    <th class="table-head">
                      {{ t('lensAdmin.columns.status') }}
                    </th>
                    <th class="table-head">
                      {{ t('lensAdmin.columns.actions') }}
                    </th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-line bg-surface">
                  <tr
                    v-for="row in dataSources"
                    :key="row.uuid"
                    class="cursor-pointer transition-colors hover:bg-line-soft"
                    :class="selectedDataSource?.uuid === row.uuid ? 'bg-brand-50' : ''"
                    @click="selectDataSource(row)"
                  >
                    <td class="table-cell">
                      <div class="font-medium text-ink-900">
                        {{ row.name }}
                      </div>
                      <div class="mt-1 flex flex-wrap items-center gap-2">
                        <span class="font-mono text-xs text-ink-400">
                          {{ compactUuid(row.uuid) }}
                        </span>
                        <span class="rounded border border-line bg-surface-sunken px-1.5 py-0.5 text-xs text-ink-500">
                          {{ formatSourceType(row.source_type) }}
                        </span>
                      </div>
                    </td>
                    <td class="table-cell max-w-xs text-ink-600">
                      <div class="truncate" :title="dataSourceRepository(row)">
                        {{ dataSourceRepository(row) }}
                      </div>
                    </td>
                    <td class="table-cell font-mono text-xs text-ink-500">
                      {{ dataSourceBranch(row) }}
                    </td>
                    <td class="table-cell text-ink-600">
                      {{ row.lensnode_name || lensNodeName(row.lensnode) }}
                    </td>
                    <td class="table-cell max-w-xs font-mono text-xs text-ink-500">
                      <div class="truncate" :title="row.target_path || emptyValue">
                        {{ row.target_path || emptyValue }}
                      </div>
                    </td>
                    <td class="table-cell text-ink-600">
                      <div class="space-y-2">
                        <div class="flex flex-wrap items-center gap-2">
                          <StatusBadge
                            :status="
                              isDataSourceSyncing(row)
                                ? 'processing'
                                : 'pending'
                            "
                          />
                          <span class="text-sm text-ink-600">
                            {{ formatDataSourceSyncState(row) }}
                          </span>
                        </div>
                        <div
                          v-if="isDataSourceSyncing(row)"
                          class="space-y-1 text-xs text-ink-500"
                        >
                          <div class="break-words">
                            {{ row.current_sync?.progress_message || row.current_sync?.progress_step || emptyValue }}
                          </div>
                          <div class="font-mono">
                            {{ compactUuid(row.current_sync?.task_id) }}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td class="table-cell">
                      <StatusBadge :status="row.status" />
                    </td>
                    <td class="table-cell" @click.stop>
                      <div class="flex flex-wrap gap-2">
                        <BaseButton
                          size="sm"
                          variant="outline"
                          :disabled="isDataSourceSyncing(row)"
                          @click="sync(row)"
                        >
                          {{ t('lensAdmin.actions.sync') }}
                        </BaseButton>
                        <BaseButton
                          v-if="isDataSourceSyncing(row)"
                          size="sm"
                          variant="danger"
                          @click="cancelSync(row)"
                        >
                          {{ t('lensAdmin.actions.cancelSync') }}
                        </BaseButton>
                        <BaseButton
                          v-if="row.current_sync?.id"
                          size="sm"
                          variant="outline"
                          @click="openDataSourceTask(row)"
                        >
                          {{ t('lensAdmin.actions.viewTask') }}
                        </BaseButton>
                        <RowActions :row="row" />
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>

          </div>

          <div
            v-else
            class="relative overflow-x-auto rounded-lg border border-line bg-surface"
          >
            <table class="min-w-full divide-y divide-line">
              <thead class="bg-surface-sunken">
                <tr>
                  <th
                    v-for="column in activeColumns"
                    :key="column"
                    class="table-head"
                  >
                    {{ column }}
                  </th>
                </tr>
              </thead>
              <tbody class="divide-y divide-line bg-surface">
                <tr
                  v-for="row in activeRows"
                  :key="row.uuid || row.key || row.task_type"
                  class="transition-colors hover:bg-line-soft"
                >
                  <template v-if="activeTab === 'assistants'">
                    <td class="table-cell">
                      <div class="font-medium text-ink-900">
                        {{ row.name }}
                      </div>
                      <div class="mt-1 font-mono text-xs text-ink-400">
                        {{ row.slug }}
                      </div>
                    </td>
                    <td class="table-cell text-ink-600">
                      {{ lensNodeName(row.lensnode) }}
                    </td>
                    <td class="table-cell text-ink-600">
                      {{ row.selected_task || emptyValue }}
                    </td>
                    <td class="table-cell font-mono text-xs text-ink-500">
                      {{ row.selected_dirs?.[0]?.path || emptyValue }}
                    </td>
                    <td class="table-cell text-ink-600">
                      {{
                        t('lensAdmin.table.toolSummary', {
                          skills: row.skill_summary?.enabled || 0,
                          mcps: row.mcp_summary?.enabled || 0
                        })
                      }}
                    </td>
                    <td class="table-cell">
                      <StatusBadge :status="row.status" />
                    </td>
                    <td class="table-cell">
                      <RowActions :row="row" />
                    </td>
                  </template>

                  <template v-else-if="activeTab === 'lensnodes'">
                    <td class="table-cell">
                      <div class="font-medium text-ink-900">
                        {{ row.name }}
                      </div>
                      <div class="mt-1 font-mono text-xs text-ink-400">
                        {{ compactUuid(row.uuid) }}
                      </div>
                    </td>
                    <td class="table-cell">
                      <div class="flex flex-wrap gap-1">
                        <StatusBadge :status="row.status" />
                        <StatusBadge :status="row.enrollment_status" />
                      </div>
                    </td>
                    <td class="table-cell text-ink-600">
                      {{ row.workspace_path || emptyValue }}
                    </td>
                    <td class="table-cell text-ink-600">
                      {{
                        t('lensAdmin.table.dirTaskSummary', {
                          dirs: row.available_dirs?.length || 0,
                          tasks: row.tasks?.length || 0
                        })
                      }}
                    </td>
                    <td class="table-cell text-ink-600">
                      {{ formatDateTime(row.last_heartbeat_at) }}
                    </td>
                    <td class="table-cell">
                      <div class="flex flex-wrap gap-2">
                        <BaseButton
                          size="sm"
                          variant="outline"
                          @click="startEdit(row)"
                        >
                          {{ t('common.edit') }}
                        </BaseButton>
                        <BaseButton
                          v-if="row.enrollment_status !== 'approved'"
                          size="sm"
                          variant="outline"
                          @click="approve(row)"
                        >
                          {{ t('lensAdmin.actions.approve') }}
                        </BaseButton>
                        <BaseButton
                          size="sm"
                          variant="outline"
                          @click="issueToken(row)"
                        >
                          {{ t('lensAdmin.actions.issueToken') }}
                        </BaseButton>
                        <BaseButton
                          size="sm"
                          variant="outline"
                          @click="revokeToken(row)"
                        >
                          {{ t('lensAdmin.actions.revokeToken') }}
                        </BaseButton>
                        <BaseButton
                          size="sm"
                          variant="danger"
                          @click="remove(row)"
                        >
                          {{ t('common.delete') }}
                        </BaseButton>
                      </div>
                    </td>
                  </template>

                  <template v-else-if="activeTab === 'skills'">
                    <td class="table-cell font-medium text-ink-900">
                      {{ row.name }}
                    </td>
                    <td class="table-cell font-mono text-ink-500">
                      {{ row.slug }}
                    </td>
                    <td class="table-cell">
                      <StatusBadge
                        :status="row.enabled ? 'enabled' : 'disabled'"
                      />
                    </td>
                    <td class="table-cell">
                      <RowActions :row="row" />
                    </td>
                  </template>

                  <template v-else-if="activeTab === 'credentials'">
                    <td class="table-cell">
                      <div class="font-medium text-ink-900">
                        {{ row.name }}
                      </div>
                      <div class="mt-1 text-xs text-ink-500">
                        {{
                          row.has_secret
                            ? t('lensAdmin.credentials.secretConfigured')
                            : t('lensAdmin.credentials.secretMissing')
                        }}
                      </div>
                    </td>
                    <td class="table-cell text-ink-600">
                      {{ credentialProviderLabel(row.provider) }}
                    </td>
                    <td class="table-cell text-ink-600">
                      {{ credentialAuthTypeLabel(row.auth_type) }}
                    </td>
                    <td class="table-cell text-ink-600">
                      {{ row.datasource_count || 0 }}
                    </td>
                    <td class="table-cell text-ink-600">
                      {{ formatDateTime(row.last_used_at) }}
                    </td>
                    <td class="table-cell">
                      <RowActions :row="row" />
                    </td>
                  </template>

                  <template v-else-if="activeTab === 'mcp'">
                    <td class="table-cell font-medium text-ink-900">
                      {{ row.name }}
                    </td>
                    <td class="table-cell font-mono text-ink-500">
                      {{ row.transport }}
                    </td>
                    <td class="table-cell font-mono text-ink-500">
                      {{ row.endpoint || emptyValue }}
                    </td>
                    <td class="table-cell">
                      <StatusBadge
                        :status="row.enabled ? 'enabled' : 'disabled'"
                      />
                    </td>
                    <td class="table-cell">
                      <RowActions :row="row" />
                    </td>
                  </template>

                  <template v-else>
                    <td class="table-cell font-medium text-ink-900">
                      {{ formatTaskName(row) }}
                    </td>
                    <td class="table-cell font-mono text-ink-500">
                      {{ row.task_type || emptyValue }}
                    </td>
                    <td class="table-cell">
                      <StatusBadge :status="row.last_status || 'pending'" />
                    </td>
                    <td
                      class="table-cell"
                      :class="row.last_error ? 'text-danger-700' : 'text-ink-400'"
                    >
                      {{ row.last_error || emptyValue }}
                    </td>
                    <td class="table-cell text-ink-500">
                      {{ formatDateTime(row.last_run_at) }}
                    </td>
                    <td class="table-cell">
                      <BaseButton
                        size="sm"
                        variant="outline"
                        :loading="loading"
                        @click="load"
                      >
                        {{ t('common.refresh') }}
                      </BaseButton>
                    </td>
                  </template>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
    </section>

      <!-- Assistant Drawer (create wizard + edit) -->
      <AssistantFormDrawer
        :show="showDrawer && activeTab === 'assistants'"
        :mode="mode"
        :form="form"
        :lensnodes="lensnodes"
        :skills="skills"
        :mcps="mcps"
        :llm-config-options="llmConfigOptions"
        :saving="saving"
        :form-error="formError"
        :refreshing-dirs="refreshingDirs"
        @close="closeDrawer"
        @save="save"
        @refresh-dirs="refreshDirs"
      />

      <DataSourceFormDrawer
        :show="showDrawer && activeTab === 'datasources'"
        :mode="mode"
        :form="form"
        :config="datasourceConfig"
        :lensnodes="lensnodes"
        :credentials="credentials"
        v-model:sync-interval-seconds="syncIntervalSeconds"
        v-model:sync-policy-mode="syncPolicyMode"
        v-model:sync-cron="syncCron"
        v-model:sync-timezone="syncTimezone"
        :path-result="datasourcePathResult"
        :connection-result="datasourceConnectionResult"
        :checking-path="checkingDatasourcePath"
        :testing-connection="testingDatasourceConnection"
        :saving="saving"
        :form-error="formError"
        @close="closeDrawer"
        @save="save"
        @type-change="handleDatasourceTypeChange"
        @check-path="checkDatasourcePath"
        @test-connection="testDatasourceConnection"
        @connection-change="resetDatasourceConnectionResult"
        @create-credential="createInlineCredential"
      />

      <BaseDrawer
        :show="showDatasourceDetailDrawer"
        :title="t('lensAdmin.datasourceDetail.title')"
        :subtitle="selectedDataSource?.name || ''"
        width="2xl"
        @close="closeDataSourceDetail"
      >
        <template #actions>
          <BaseButton
            v-if="selectedDataSource?.current_sync?.id"
            size="sm"
            variant="outline"
            @click="openDataSourceTask(selectedDataSource)"
          >
            {{ t('lensAdmin.actions.viewTask') }}
          </BaseButton>
        </template>
        <div v-if="selectedDataSource" class="space-y-6">
          <section>
            <h3 class="mb-4 text-sm font-semibold text-ink-900">
              {{ t('lensAdmin.datasourceDetail.basicInfo') }}
            </h3>
            <dl class="grid grid-cols-1 gap-4">
              <div>
                <dt class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600">
                  {{ t('lensAdmin.fields.name') }}
                </dt>
                <dd class="break-words text-sm font-medium text-ink-900">
                  {{ selectedDataSource.name || emptyValue }}
                </dd>
              </div>
              <div>
                <dt class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600">
                  UUID
                </dt>
                <dd class="break-words font-mono text-xs font-medium text-ink-900">
                  {{ selectedDataSource.uuid }}
                </dd>
              </div>
              <div>
                <dt class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600">
                  {{ t('lensAdmin.fields.status') }}
                </dt>
                <dd>
                  <StatusBadge :status="selectedDataSource.status" />
                </dd>
              </div>
            </dl>
          </section>

          <section class="border-t border-line pt-6">
            <h3 class="mb-4 text-sm font-semibold text-ink-900">
              {{ t('lensAdmin.datasourceDetail.connection') }}
            </h3>
            <dl class="grid grid-cols-1 gap-4">
              <div
                v-for="item in datasourceConnectionDetails"
                :key="item.label"
              >
                <dt class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600">
                  {{ item.label }}
                </dt>
                <dd
                  class="break-words text-sm font-medium text-ink-900"
                  :class="item.mono ? 'font-mono text-xs' : ''"
                >
                  {{ item.value }}
                </dd>
              </div>
            </dl>
          </section>

          <section class="border-t border-line pt-6">
            <h3 class="mb-4 text-sm font-semibold text-ink-900">
              {{ t('lensAdmin.datasourceDetail.sync') }}
            </h3>
            <dl class="grid grid-cols-1 gap-4">
              <div
                v-for="item in datasourceSyncDetails"
                :key="item.label"
              >
                <dt class="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-600">
                  {{ item.label }}
                </dt>
                <dd
                  class="break-words text-sm font-medium text-ink-900"
                  :class="item.mono ? 'font-mono text-xs' : ''"
                >
                  {{ item.value }}
                </dd>
              </div>
            </dl>
          </section>
        </div>
        <div v-else class="py-12 text-center text-sm text-ink-500">
          {{ t('lensAdmin.datasourceDetail.selectHint') }}
        </div>
      </BaseDrawer>

      <BaseModal :show="showModal" :title="modalTitle" @close="closeModal">
        <form class="space-y-4" @submit.prevent="save">
          <template v-if="activeTab === 'lensnodes'">
            <FormRow :label="t('lensAdmin.fields.name')">
              <input v-model="form.name" class="form-input" required />
            </FormRow>
            <div class="grid gap-4 md:grid-cols-3">
              <FormRow :label="t('lensAdmin.fields.workspacePath')">
                <input v-model="form.workspace_path" class="form-input" />
              </FormRow>
              <FormRow :label="t('lensAdmin.fields.protocolVersion')">
                <input v-model="form.protocol_version" class="form-input" />
              </FormRow>
              <FormRow :label="t('lensAdmin.fields.agentVersion')">
                <input v-model="form.agent_version" class="form-input" />
              </FormRow>
            </div>
            <FormRow :label="t('lensAdmin.fields.labels')">
              <KeyValueEditor
                v-model="form.labels_rows"
                :key-label="t('lensAdmin.fields.labelKey')"
                :value-label="t('lensAdmin.fields.labelValue')"
              />
            </FormRow>
          </template>

          <template v-else-if="activeTab === 'skills'">
            <FormRow :label="t('lensAdmin.fields.name')">
              <input v-model="form.name" class="form-input" required />
            </FormRow>
            <FormRow :label="t('lensAdmin.fields.slug')">
              <input v-model="form.slug" class="form-input" required />
            </FormRow>
            <FormRow :label="t('lensAdmin.fields.definition')">
              <textarea
                v-model="form.definition_text"
                class="json-input"
                rows="6"
              />
            </FormRow>
            <BooleanRow v-model="form.enabled" />
          </template>

          <template v-else-if="activeTab === 'mcp'">
            <FormRow :label="t('lensAdmin.fields.name')">
              <input v-model="form.name" class="form-input" required />
            </FormRow>
            <div class="grid gap-4 md:grid-cols-2">
              <FormRow :label="t('lensAdmin.fields.transport')">
                <select v-model="form.transport" class="form-input">
                  <option value="url">url</option>
                  <option value="stdio">stdio</option>
                </select>
              </FormRow>
              <FormRow :label="t('lensAdmin.fields.endpoint')">
                <input v-model="form.endpoint" class="form-input" />
              </FormRow>
            </div>
            <FormRow :label="t('lensAdmin.fields.config')">
              <KeyValueEditor
                v-model="form.config_rows"
                :key-label="t('lensAdmin.fields.configKey')"
                :value-label="t('lensAdmin.fields.configValue')"
              />
            </FormRow>
            <BooleanRow v-model="form.enabled" />
          </template>

          <template v-else-if="activeTab === 'credentials'">
            <FormRow :label="t('lensAdmin.fields.name')">
              <input v-model="form.name" class="form-input" required />
            </FormRow>
            <div class="grid gap-4 md:grid-cols-2">
              <FormRow :label="t('lensAdmin.fields.type')">
                <select v-model="form.provider" class="form-input">
                  <option value="generic">Git</option>
                  <option value="feishu">Feishu</option>
                </select>
              </FormRow>
              <FormRow :label="t('lensAdmin.fields.authScheme')">
                <div class="form-input bg-surface-sunken text-ink-500">
                  {{ credentialAuthTypeLabel(credentialFormAuthType) }}
                </div>
              </FormRow>
            </div>
            <template v-if="credentialFormAuthType === 'feishu_app'">
              <div class="grid gap-4 md:grid-cols-2">
                <FormRow :label="t('lensAdmin.fields.feishuAppId')">
                  <input
                    v-model="form.app_id"
                    class="form-input"
                    autocomplete="off"
                  />
                </FormRow>
                <FormRow :label="t('lensAdmin.fields.feishuAppSecret')">
                  <input
                    v-model="form.app_secret"
                    class="form-input"
                    type="password"
                    autocomplete="off"
                  />
                </FormRow>
              </div>
            </template>
            <FormRow
              v-else
              :label="t('lensAdmin.fields.accessToken')"
            >
              <input
                v-model="form.secret"
                class="form-input"
                type="password"
                autocomplete="off"
              />
            </FormRow>
            <p
              v-if="mode === 'edit'"
              class="-mt-2 text-xs text-ink-500"
            >
              {{ t('lensAdmin.credentials.replaceHint') }}
            </p>
          </template>

          <p v-if="formError" class="text-sm text-danger-700">
            {{ formError }}
          </p>
        </form>
        <template #footer>
          <div class="flex flex-row-reverse gap-2">
            <BaseButton :loading="saving" variant="primary" @click="save">
              {{ t('common.save') }}
            </BaseButton>
            <BaseButton variant="outline" @click="closeModal">
              {{ t('common.cancel') }}
            </BaseButton>
          </div>
        </template>
      </BaseModal>
    </div>
  </AdminLayout>
</template>

<script setup>
import { computed, defineComponent, h, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { llmAdminApi } from '@/admin/api/llmAdmin'
import AdminLayout from '@/admin/layout/AdminLayout.vue'
import {
  approveLensNode,
  cancelDataSourceSync,
  checkLensNodeDataSourcePath,
  createAssistant,
  createCredential,
  createDataSource,
  createGlobalSetting,
  createLensNode,
  createMcpServer,
  createSkill,
  deleteAssistant,
  deleteCredential,
  deleteDataSource,
  deleteLensNode,
  deleteMcpServer,
  deleteSkill,
  getSystemHealth,
  issueLensNodeToken,
  listAssistants,
  listCredentials,
  listDataSources,
  listGlobalSettings,
  listLensNodes,
  listMcpServers,
  listSkills,
  revokeLensNodeToken,
  syncDataSource,
  testLensNodeDataSourceConnection,
  updateAssistant,
  updateCredential,
  updateDataSource,
  updateGlobalSetting,
  updateLensNode,
  updateMcpServer,
  updateSkill,
  updateSystemTaskEnabled
} from '@/api/lens'
import { useToast } from '@/composables/useToast'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import BaseModal from '@/components/ui/BaseModal.vue'
import StatusBadge from '@/components/ui/StatusBadge.vue'

import AssistantFormDrawer from './AssistantFormDrawer.vue'
import DataSourceFormDrawer from './DataSourceFormDrawer.vue'
import {
  EMPTY_VALUE as emptyValue,
  compactUuid,
  formatLLMConfigLabel,
  formatTaskName,
  listToText,
  normalizeList,
  objectToRows,
  rowsToObject,
  selectedDirsFromValue,
  splitList,
  stringifyJson
} from './adminHelpers'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const { showSuccess, showError } = useToast()

const routeToTab = {
  assistants: 'assistants',
  lensnodes: 'lensnodes',
  datasources: 'datasources',
  'resources/credentials': 'credentials',
  'resources/skills': 'skills',
  'resources/mcp': 'mcp',
  settings: 'settings'
}

const activeTab = ref('assistants')
const loading = ref(false)
const saving = ref(false)
const pendingDeleteId = ref(null)
const refreshingDirs = ref(false)
const showModal = ref(false)
const showDrawer = ref(false)
const showDatasourceDetailDrawer = ref(false)
const mode = ref('create')
const form = ref({})
const formError = ref('')
const datasourceConfig = ref({})
const datasourcePathResult = ref(null)
const datasourceConnectionResult = ref(null)
const suppressDatasourceConnectionReset = ref(false)
const datasourceConnectionBaseSignature = ref('')
const checkingDatasourcePath = ref(false)
const testingDatasourceConnection = ref(false)
const syncIntervalSeconds = ref(3600)
const syncPolicyMode = ref('interval')
const syncCron = ref('0 2 * * *')
const syncTimezone = ref('Asia/Shanghai')
const llmConfigOptions = ref([])

const assistants = ref([])
const lensnodes = ref([])
const dataSources = ref([])
const selectedDataSource = ref(null)
const credentials = ref([])
const skills = ref([])
const mcps = ref([])
const globalSettings = ref([])
const systemHealth = ref([])
const taskSaving = ref({})

const defaultSettings = {
  'lensnode.defaults.timeout': 600,
  'retention.run_days': 90,
  'lensnode.health.offline_threshold_s': 120,
  'lensnode_cleanup.interval_seconds': 3600,
  'lensnode_health.interval_seconds': 60,
  'run_retention.interval_seconds': 86400,
  'lens.skills.generator_model_ref': ''
}

const settingsForm = ref({ ...defaultSettings })
const initialSettings = ref({ ...defaultSettings })

const defaultScheduledTaskMeta = {
  lensnode_cleanup: {
    label: () => t('lensAdmin.tasks.cleanup'),
    description: () => t('lensAdmin.tasks.cleanupDesc')
  },
  lensnode_health: {
    label: () => t('lensAdmin.tasks.health'),
    description: () => t('lensAdmin.tasks.healthDesc')
  },
  run_retention: {
    label: () => t('lensAdmin.tasks.retention'),
    description: () => t('lensAdmin.tasks.retentionDesc')
  }
}

const FormRow = defineComponent({
  props: {
    label: {
      type: String,
      required: true
    }
  },
  setup(props, { slots }) {
    return () =>
      h('div', [
        h(
          'label',
          { class: 'mb-1 block text-sm font-medium text-ink-700' },
          props.label
        ),
        slots.default?.()
      ])
  }
})

const BooleanRow = defineComponent({
  props: {
    modelValue: {
      type: Boolean,
      default: true
    }
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () =>
      h('label', { class: 'flex items-center gap-2 text-sm text-ink-600' }, [
        h('input', {
          checked: props.modelValue,
          class:
            'h-4 w-4 rounded border-line text-brand-600 focus:ring-brand-500',
          type: 'checkbox',
          onChange: (event) => emit('update:modelValue', event.target.checked)
        }),
        h('span', t('lensAdmin.fields.enabled'))
      ])
  }
})

const KeyValueEditor = defineComponent({
  props: {
    keyLabel: {
      type: String,
      required: true
    },
    modelValue: {
      type: Array,
      default: () => []
    },
    valueLabel: {
      type: String,
      required: true
    }
  },
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    const updateRow = (index, field, value) => {
      const rows = props.modelValue.map((row) => ({ ...row }))
      rows[index] = { ...rows[index], [field]: value }
      emit('update:modelValue', rows)
    }

    const removeRow = (index) => {
      emit(
        'update:modelValue',
        props.modelValue.filter((_, rowIndex) => rowIndex !== index)
      )
    }

    const addRow = () => {
      emit('update:modelValue', [...props.modelValue, { key: '', value: '' }])
    }

    return () =>
      h('div', { class: 'space-y-2' }, [
        ...props.modelValue.map((row, index) =>
          h(
            'div',
            {
              class:
                'grid grid-cols-1 gap-2 rounded-md border border-line bg-surface-sunken p-2 md:grid-cols-[1fr_1fr_auto]'
            },
            [
              h('input', {
                class:
                  'rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20',
                placeholder: props.keyLabel,
                value: row.key,
                onInput: (event) => updateRow(index, 'key', event.target.value)
              }),
              h('input', {
                class:
                  'rounded-md border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20',
                placeholder: props.valueLabel,
                value: row.value,
                onInput: (event) =>
                  updateRow(index, 'value', event.target.value)
              }),
              h(
                BaseButton,
                {
                  size: 'sm',
                  variant: 'outline',
                  onClick: () => removeRow(index)
                },
                () => t('lensAdmin.actions.removeRow')
              )
            ]
          )
        ),
        h(
          BaseButton,
          {
            size: 'sm',
            variant: 'outline',
            onClick: addRow
          },
          () => t('lensAdmin.actions.addRow')
        )
      ])
  }
})

const RowActions = defineComponent({
  props: {
    row: {
      type: Object,
      required: true
    }
  },
  setup(props) {
    return () => {
      const id = props.row.uuid || props.row.key
      if (pendingDeleteId.value === id) {
        return h('div', { class: 'flex flex-wrap items-center gap-2' }, [
          h(
            BaseButton,
            {
              size: 'sm',
              variant: 'danger',
              onClick: () => {
                pendingDeleteId.value = null
                remove(props.row)
              }
            },
            () => t('common.confirm')
          ),
          h(
            BaseButton,
            {
              size: 'sm',
              variant: 'outline',
              onClick: () => {
                pendingDeleteId.value = null
              }
            },
            () => t('common.cancel')
          )
        ])
      }
      return h('div', { class: 'flex flex-wrap gap-2' }, [
        h(
          BaseButton,
          {
            size: 'sm',
            variant: 'outline',
            onClick: () => startEdit(props.row)
          },
          () => t('common.edit')
        ),
        h(
          BaseButton,
          {
            size: 'sm',
            variant: 'danger',
            onClick: () => {
              pendingDeleteId.value = id
            }
          },
          () => t('common.delete')
        )
      ])
    }
  }
})

const activeRows = computed(() => {
  const rowsByTab = {
    assistants: assistants.value,
    lensnodes: lensnodes.value,
    datasources: dataSources.value,
    credentials: credentials.value,
    skills: skills.value,
    mcp: mcps.value
  }
  return rowsByTab[activeTab.value] || []
})

const activeCount = computed(() => {
  if (activeTab.value === 'settings') {
    return settingDefinitions.value.length
  }
  return activeRows.value.length
})

const canCreate = computed(
  () => activeTab.value !== 'settings'
)

const activeMeta = computed(() => {
  const key = activeTab.value
  return {
    title: t(`lensAdmin.pages.${key}.title`),
    description: t(`lensAdmin.pages.${key}.description`),
    label: t(`lensAdmin.pages.${key}.label`),
    action: t(`lensAdmin.pages.${key}.action`)
  }
})

const activeColumns = computed(() => {
  const columnsByTab = {
    assistants: [
      'assistant',
      'lensnode',
      'task',
      'dirs',
      'tools',
      'status',
      'actions'
    ],
    lensnodes: [
      'lensnode',
      'status',
      'workspace',
      'dirsAndTasks',
      'heartbeat',
      'actions'
    ],
    datasources: [
      'datasource',
      'type',
      'lensnode',
      'targetPath',
      'sync',
      'status',
      'actions'
    ],
    credentials: [
      'credential',
      'type',
      'authScheme',
      'datasources',
      'lastUsedAt',
      'actions'
    ],
    skills: ['skill', 'slug', 'status', 'actions'],
    mcp: ['mcpServer', 'transport', 'endpoint', 'status', 'actions']
  }
  return (columnsByTab[activeTab.value] || []).map((column) =>
    t(`lensAdmin.columns.${column}`)
  )
})

const credentialFormAuthType = computed(() =>
  form.value.provider === 'feishu' ? 'feishu_app' : 'https_token'
)

const defaultScheduledTasks = computed(() => {
  const taskTypes = [
    'lensnode_cleanup',
    'lensnode_health',
    'run_retention'
  ]
  return taskTypes.map((taskType) => {
    const existing =
      systemHealth.value.find((row) => row.task_type === taskType) || {}
    const meta = defaultScheduledTaskMeta[taskType]
    return {
      task_type: taskType,
      label: meta.label(),
      description: meta.description(),
      enabled: existing.enabled !== false,
      last_run_at: existing.last_run_at || null,
      last_status: existing.last_status || null
    }
  })
})

const settingDefinitions = computed(() => [
  {
    key: 'lensnode.defaults.timeout',
    label: t('lensAdmin.settings.timeoutTitle'),
    description: t('lensAdmin.settings.timeoutDesc'),
    type: 'number',
    unit: t('lensAdmin.settings.secondsUnit')
  },
  {
    key: 'retention.run_days',
    label: t('lensAdmin.settings.retentionTitle'),
    description: t('lensAdmin.settings.retentionDesc'),
    type: 'number',
    unit: t('lensAdmin.settings.daysUnit')
  },
  {
    key: 'lensnode.health.offline_threshold_s',
    label: t('lensAdmin.settings.offlineTitle'),
    description: t('lensAdmin.settings.offlineDesc'),
    type: 'number',
    unit: t('lensAdmin.settings.secondsUnit')
  },
  {
    key: 'lensnode_cleanup.interval_seconds',
    label: t('lensAdmin.settings.cleanupIntervalTitle'),
    description: t('lensAdmin.settings.cleanupIntervalDesc'),
    type: 'number',
    unit: t('lensAdmin.settings.secondsUnit')
  },
  {
    key: 'lensnode_health.interval_seconds',
    label: t('lensAdmin.settings.healthIntervalTitle'),
    description: t('lensAdmin.settings.healthIntervalDesc'),
    type: 'number',
    unit: t('lensAdmin.settings.secondsUnit')
  },
  {
    key: 'run_retention.interval_seconds',
    label: t('lensAdmin.settings.retentionIntervalTitle'),
    description: t('lensAdmin.settings.retentionIntervalDesc'),
    type: 'number',
    unit: t('lensAdmin.settings.secondsUnit')
  },
  {
    key: 'lens.skills.generator_model_ref',
    label: t('lensAdmin.settings.skillGeneratorModelTitle'),
    description: t('lensAdmin.settings.skillGeneratorModelDesc'),
    type: 'model_ref',
    unit: ''
  }
])

const modalTitle = computed(() => {
  const action =
    mode.value === 'create'
      ? t('lensAdmin.modal.create')
      : t('lensAdmin.modal.edit')
  return `${action} ${activeMeta.value.label}`
})

const selectedDatasourceLensNode = computed(() =>
  lensnodes.value.find((node) => node.uuid === form.value.lensnode_uuid)
)

const datasourceConnectionDetails = computed(() => {
  const row = selectedDataSource.value
  if (!row) return []
  const config = row.config || {}
  if (row.source_type === 'git') {
    return [
      detailItem(t('lensAdmin.fields.type'), formatSourceType(row.source_type)),
      detailItem(t('lensAdmin.fields.repoUrl'), config.repo_url, true),
      detailItem(t('lensAdmin.fields.branch'), config.branch || 'main', true),
      detailItem(t('lensAdmin.fields.authScheme'), authSchemeLabel(config.auth_scheme)),
      detailItem(
        t('lensAdmin.datasourceDetail.credential'),
        row.credential_configured
          ? t('common.status.enabled')
          : t('common.status.disabled')
      )
    ]
  }
  return [
    detailItem(t('lensAdmin.fields.type'), formatSourceType(row.source_type)),
    detailItem(
      t('lensAdmin.fields.syncScope'),
      feishuScopeLabel(config.sync_mode)
    ),
    detailItem(t('lensAdmin.fields.folderUrl'), config.folder_url, true),
    detailItem(t('lensAdmin.fields.folderToken'), config.folder_token, true),
    detailItem(t('lensAdmin.fields.documentUrl'), config.document_url, true),
    detailItem(t('lensAdmin.fields.docIds'), formatDocIds(config.doc_ids), true)
  ].filter((item) => item.value !== emptyValue)
})

const datasourceSyncDetails = computed(() => {
  const row = selectedDataSource.value
  if (!row) return []
  return [
    detailItem(t('lensAdmin.fields.lensnode'), row.lensnode_name || lensNodeName(row.lensnode)),
    detailItem(t('lensAdmin.fields.targetPath'), row.target_path, true),
    detailItem(
      t('lensAdmin.fields.syncInterval'),
      formatSyncPolicy(row.sync_policy, row.last_synced_at)
    ),
    detailItem(t('lensAdmin.datasourceDetail.lastSyncedAt'), formatDateTime(row.last_synced_at)),
    detailItem(t('lensAdmin.datasourceDetail.lastError'), row.last_error, true),
    detailItem(t('lensAdmin.datasourceDetail.createdAt'), formatDateTime(row.created_at)),
    detailItem(t('lensAdmin.datasourceDetail.updatedAt'), formatDateTime(row.updated_at))
  ]
})

function formatDateTime(value) {
  if (!value) {
    return t('lensAdmin.table.notRecorded')
  }
  return new Intl.DateTimeFormat(locale.value, {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(value))
}

function formatSyncPolicy(syncPolicy, lastSyncedAt) {
  if (syncPolicy?.mode === 'crontab') {
    const cron = syncPolicy.cron || emptyValue
    const timezone = syncPolicy.timezone || 'UTC'
    return `${cron} · ${timezone} · ${formatDateTime(lastSyncedAt)}`
  }
  const interval = syncPolicy?.interval_seconds
  const intervalText = interval
    ? t('lensAdmin.table.intervalSeconds', { seconds: interval })
    : emptyValue
  return `${intervalText} · ${formatDateTime(lastSyncedAt)}`
}

function isDataSourceSyncing(row) {
  return Boolean(row?.current_sync?.task_id)
}

function formatDataSourceSyncState(row) {
  if (isDataSourceSyncing(row)) {
    return t('lensAdmin.table.syncRunning')
  }
  return formatSyncPolicy(row.sync_policy, row.last_synced_at)
}

function openDataSourceTask(row) {
  const executionId = row?.current_sync?.id
  if (!executionId) return
  const route = router.resolve({
    path: '/management/task-management/list',
    query: { execution_id: executionId }
  })
  window.open(route.href, '_blank', 'noopener')
}

function detailItem(label, value, mono = false) {
  const normalized = Array.isArray(value) ? value.join(', ') : value
  return {
    label,
    value: normalized || emptyValue,
    mono
  }
}

function selectDataSource(row) {
  selectedDataSource.value = row
  showDatasourceDetailDrawer.value = true
}

function closeDataSourceDetail() {
  showDatasourceDetailDrawer.value = false
}

function formatSourceType(sourceType) {
  if (sourceType === 'git') {
    return 'Git'
  }
  if (sourceType === 'feishu') {
    return t('lensAdmin.datasourceWizard.feishu')
  }
  return sourceType || emptyValue
}

function authSchemeLabel(authScheme) {
  if (authScheme === 'token') {
    return t('lensAdmin.datasourceWizard.authToken')
  }
  return t('lensAdmin.datasourceWizard.authNone')
}

function credentialProviderLabel(provider) {
  if (provider === 'feishu') {
    return 'Feishu'
  }
  if (provider) {
    return 'Git'
  }
  return emptyValue
}

function credentialAuthTypeLabel(authType) {
  const labels = {
    https_token: 'HTTPS Token',
    feishu_app: 'Feishu App'
  }
  return labels[authType] || authType || emptyValue
}

function feishuScopeLabel(syncMode) {
  if (syncMode === 'drive_folder') {
    return t('lensAdmin.datasourceWizard.feishuScopeDriveFolder')
  }
  return t('lensAdmin.datasourceWizard.feishuScopeDocuments')
}

function formatDocIds(docIds) {
  if (Array.isArray(docIds)) {
    return docIds.join(', ')
  }
  return docIds || emptyValue
}

function dataSourceRepository(row) {
  const config = row.config || {}
  if (row.source_type === 'git') {
    return config.repo_url || emptyValue
  }
  return (
    config.folder_url ||
    config.folder_token ||
    config.document_url ||
    emptyValue
  )
}

function dataSourceBranch(row) {
  if (row.source_type === 'git') {
    return row.config?.branch || 'main'
  }
  return emptyValue
}

function lensNodeName(value) {
  const uuid = typeof value === 'object' ? value?.uuid : value
  const found = lensnodes.value.find((lensnode) => lensnode.uuid === uuid)
  return found?.name || uuid || emptyValue
}

function selectedDirs() {
  return Array.isArray(form.value.selected_dirs) ? form.value.selected_dirs : []
}

function parseRouteTab() {
  const raw = route.params.pathMatch
  const path = Array.isArray(raw) ? raw.join('/') : raw || 'assistants'
  activeTab.value = routeToTab[path] || 'assistants'
}


async function load() {
  loading.value = true
  formError.value = ''
  try {
    const [
      assistantRows,
      lensnodeRows,
      dataSourceRows,
      credentialRows,
      skillRows,
      mcpRows,
      settingRows,
      healthRows,
      llmRows
    ] = await Promise.all([
      listAssistants(),
      listLensNodes(),
      listDataSources(),
      listCredentials(),
      listSkills(),
      listMcpServers(),
      listGlobalSettings(),
      getSystemHealth(),
      llmAdminApi.getLLMConfigAll({ scope: 'global' }).catch(() => [])
    ])

    assistants.value = normalizeList(assistantRows)
    lensnodes.value = normalizeList(lensnodeRows)
    dataSources.value = normalizeList(dataSourceRows)
    credentials.value = normalizeList(credentialRows)
    if (activeTab.value === 'datasources') {
      const existing = dataSources.value.find(
        (row) => row.uuid === selectedDataSource.value?.uuid
      )
      selectedDataSource.value = existing || dataSources.value[0] || null
    }
    skills.value = normalizeList(skillRows)
    mcps.value = normalizeList(mcpRows)
    globalSettings.value = normalizeList(settingRows)
    systemHealth.value = normalizeList(healthRows)
    llmConfigOptions.value = normalizeList(llmRows)
    hydrateSettingsForm()
  } catch (error) {
    showError(resolveError(error, t('lensAdmin.messages.loadFailed')))
  } finally {
    loading.value = false
  }
}

function hydrateSettingsForm() {
  const next = { ...defaultSettings }
  globalSettings.value.forEach((setting) => {
    if (setting.key in next) {
      const definition = settingDefinitions.value.find(
        (item) => item.key === setting.key
      )
      next[setting.key] =
        definition?.type === 'number'
          ? Number(setting.value ?? next[setting.key])
          : setting.value ?? next[setting.key]
    }
  })
  settingsForm.value = { ...next }
  initialSettings.value = { ...next }
}

function resetSettingsForm() {
  settingsForm.value = { ...initialSettings.value }
  formError.value = ''
}

async function saveSettings() {
  saving.value = true
  formError.value = ''
  try {
    for (const setting of settingDefinitions.value) {
      const value =
        setting.type === 'number'
          ? Math.max(1, Number(settingsForm.value[setting.key]) || 1)
          : settingsForm.value[setting.key] || ''
      const payload = {
        key: setting.key,
        value,
        description: setting.description
      }
      const exists = globalSettings.value.some((row) => row.key === setting.key)
      if (exists) {
        await updateGlobalSetting(setting.key, payload)
      } else {
        await createGlobalSetting(payload)
      }
    }
    showSuccess(t('lensAdmin.messages.saveSuccess'))
    await load()
  } catch (error) {
    formError.value = resolveError(error, t('lensAdmin.messages.saveFailed'))
    showError(formError.value)
  } finally {
    saving.value = false
  }
}

async function updateScheduledTaskEnabled(taskType, enabled) {
  taskSaving.value = { ...taskSaving.value, [taskType]: true }
  try {
    await updateSystemTaskEnabled(taskType, enabled)
    await load()
    showSuccess(t('lensAdmin.messages.saveSuccess'))
  } catch (error) {
    showError(resolveError(error, t('lensAdmin.messages.saveFailed')))
  } finally {
    taskSaving.value = { ...taskSaving.value, [taskType]: false }
  }
}

function startCreate() {
  showDatasourceDetailDrawer.value = false
  mode.value = 'create'
  formError.value = ''
  datasourceConfig.value = {}
  datasourcePathResult.value = null
  datasourceConnectionResult.value = null
  syncIntervalSeconds.value = 3600
  form.value = defaultForm(activeTab.value)
  if (['assistants', 'datasources'].includes(activeTab.value)) {
    showDrawer.value = true
  } else {
    showModal.value = true
  }
}

function startEdit(row) {
  showDatasourceDetailDrawer.value = false
  mode.value = 'edit'
  formError.value = ''
  datasourceConfig.value = { ...(row.config || {}) }
  datasourcePathResult.value = null
  datasourceConnectionResult.value = null
  syncIntervalSeconds.value = row.sync_policy?.interval_seconds || 3600
  form.value = formFromRow(activeTab.value, row)
  if (['assistants', 'datasources'].includes(activeTab.value)) {
    showDrawer.value = true
  } else {
    showModal.value = true
  }
}

function closeModal() {
  showModal.value = false
  form.value = {}
  formError.value = ''
}

function closeDrawer() {
  showDrawer.value = false
  form.value = {}
  formError.value = ''
  datasourcePathResult.value = null
  datasourceConnectionResult.value = null
  resetDatasourceSyncPolicy()
}

async function refreshDirs() {
  if (!form.value.lensnode_uuid) return
  refreshingDirs.value = true
  try {
    lensnodes.value = normalizeList(await listLensNodes())
  } catch {
    showError(t('lensAdmin.messages.loadFailed'))
  } finally {
    refreshingDirs.value = false
  }
}

function defaultForm(tab) {
  const forms = {
    assistants: {
      name: '',
      slug: '',
      lensnode_uuid: '',
      selected_task: '',
      selected_dirs: [],
      agent_model_ref: '',
      agent_rounds: 'balanced',
      max_concurrency: 5,
      multimodal_model_ref: '',
      exclude_extensions_text: '.lock,.pyc,.sqlite3',
      exclude_dirs_text: '.git,.venv,__pycache__,node_modules,dist,build',
      workspace_guide_overview: '',
      pre_prompt: '',
      post_prompt: '',
      skill_uuids: [],
      mcp_uuids: [],
      settings: {},
      status: 'active'
    },
    lensnodes: {
      name: '',
      workspace_path: '/workspace',
      protocol_version: 'v1',
      agent_version: '',
      labels_rows: []
    },
    datasources: {
      name: '',
      source_type: 'git',
      lensnode_uuid: '',
      workspace_relative_path: '',
      target_path: '',
      credential_uuid: '',
      credential_configured: false,
      status: 'active'
    },
    credentials: {
      name: '',
      provider: 'generic',
      secret: '',
      app_id: '',
      app_secret: ''
    },
    skills: {
      name: '',
      slug: '',
      definition_text: '',
      enabled: true
    },
    mcp: {
      name: '',
      transport: 'url',
      endpoint: '',
      config_rows: [],
      enabled: true
    }
  }
  handleDatasourceTypeChange(forms[tab])
  return forms[tab] || {}
}

function formFromRow(tab, row) {
  if (tab === 'assistants') {
    return {
      uuid: row.uuid,
      name: row.name || '',
      slug: row.slug || '',
      lensnode_uuid: row.lensnode?.uuid || row.lensnode || '',
      selected_task: row.selected_task || '',
      selected_dirs: selectedDirsFromValue(row.selected_dirs || []),
      agent_model_ref: row.agent_model_ref || '',
      agent_rounds: row.agent_rounds || 'balanced',
      max_concurrency: row.max_concurrency ?? 5,
      multimodal_model_ref: row.multimodal_model_ref || '',
      exclude_extensions_text: listToText(
        row.settings?.retrieval_policy?.exclude_extensions || [
          '.lock',
          '.pyc',
          '.sqlite3'
        ]
      ),
      exclude_dirs_text: listToText(
        row.settings?.retrieval_policy?.exclude_dirs || [
          '.git',
          '.venv',
          '__pycache__',
          'node_modules',
          'dist',
          'build'
        ]
      ),
      workspace_guide_overview: row.workspace_guide?.content || '',
      pre_prompt: row.settings?.pre_prompt || '',
      post_prompt: row.settings?.post_prompt || '',
      skill_uuids: (row.skill_bindings || []).map((b) => b.skill?.uuid || b.skill_uuid).filter(Boolean),
      mcp_uuids: (row.mcp_bindings || []).map((b) => b.mcp_server?.uuid || b.mcp_uuid).filter(Boolean),
      settings: { ...(row.settings || {}) },
      status: row.status || 'active'
    }
  }
  if (tab === 'lensnodes') {
    return {
      uuid: row.uuid,
      name: row.name || '',
      workspace_path: row.workspace_path || '/workspace',
      protocol_version: row.protocol_version || 'v1',
      agent_version: row.agent_version || '',
      labels_rows: objectToRows(row.labels || {})
    }
  }
  if (tab === 'datasources') {
    const lensnodeUuid = row.lensnode?.uuid || row.lensnode || ''
    datasourceConfig.value = datasourceConfigFromRow(row)
    hydrateDatasourceSyncPolicy(row.sync_policy || {})
    return {
      uuid: row.uuid,
      name: row.name || '',
      source_type: row.source_type || 'git',
      lensnode_uuid: lensnodeUuid,
      workspace_relative_path: workspaceRelativePath(
        row.target_path || '',
        lensnodeUuid
      ),
      target_path: row.target_path || '',
      credential_uuid: row.credential || '',
      credential_configured: !!row.credential_configured,
      status: row.status || 'active'
    }
  }
  if (tab === 'skills') {
    return {
      uuid: row.uuid,
      name: row.name || '',
      slug: row.slug || '',
      definition_text:
        typeof row.definition === 'string'
          ? row.definition
          : stringifyJson(row.definition || {}),
      enabled: row.enabled !== false
    }
  }
  if (tab === 'credentials') {
    return {
      uuid: row.uuid,
      name: row.name || '',
      provider: row.auth_type === 'feishu_app' ? 'feishu' : 'generic',
      secret: '',
      app_id: '',
      app_secret: ''
    }
  }
  if (tab === 'mcp') {
    return {
      uuid: row.uuid,
      name: row.name || '',
      transport: row.transport || 'url',
      endpoint: row.endpoint || '',
      config_rows: objectToRows(row.config || {}),
      enabled: row.enabled !== false
    }
  }
  return {}
}

function datasourceConfigFromRow(row) {
  if (row.source_type === 'feishu') {
    return {
      ...(row.config || {}),
      sync_mode: row.config?.sync_mode || 'document_list',
      doc_ids_text: (row.config?.doc_ids || []).join(','),
      recursive: row.config?.recursive !== false,
      max_depth: row.config?.max_depth || 10
    }
  }
  const config = { ...(row.config || {}) }
  delete config.access_token
  return config
}

function handleDatasourceTypeChange(seed = null) {
  datasourcePathResult.value = null
  datasourceConnectionResult.value = null
  resetDatasourceSyncPolicy()
  if (!seed) {
    form.value.credential_uuid = ''
  }
  const sourceType = seed?.source_type || form.value.source_type
  if (sourceType === 'git') {
    datasourceConfig.value = {
      repo_url: '',
      branch: '',
      auth_scheme: 'none'
    }
  } else if (sourceType === 'feishu') {
    datasourceConfig.value = {
      sync_mode: 'document_list',
      document_url: '',
      doc_ids_text: '',
      folder_url: '',
      folder_token: '',
      recursive: true,
      max_depth: 10
    }
  }
}

function resetDatasourceSyncPolicy() {
  syncPolicyMode.value = 'interval'
  syncIntervalSeconds.value = 3600
  syncCron.value = '0 2 * * *'
  syncTimezone.value = 'Asia/Shanghai'
}

function hydrateDatasourceSyncPolicy(syncPolicy) {
  if ((syncPolicy.mode || 'interval') === 'crontab') {
    syncPolicyMode.value = 'crontab'
    syncCron.value = syncPolicy.cron || '0 2 * * *'
    syncTimezone.value = syncPolicy.timezone || 'Asia/Shanghai'
    return
  }
  syncPolicyMode.value = 'interval'
  syncIntervalSeconds.value = Number(syncPolicy.interval_seconds) || 3600
  syncCron.value = '0 2 * * *'
  syncTimezone.value = 'Asia/Shanghai'
}

async function save() {
  saving.value = true
  formError.value = ''
  try {
    if (activeTab.value === 'datasources' && !canSaveDatasource()) {
      throw new Error(t('lensAdmin.datasourceWizard.connectionRequired'))
    }
    const payload = buildPayload(activeTab.value)
    const uuid = form.value.uuid
    if (activeTab.value === 'assistants') {
      await saveByMode(uuid, payload, createAssistant, updateAssistant)
    } else if (activeTab.value === 'lensnodes') {
      await saveByMode(uuid, payload, createLensNode, updateLensNode)
    } else if (activeTab.value === 'datasources') {
      await saveByMode(uuid, payload, createDataSource, updateDataSource)
    } else if (activeTab.value === 'credentials') {
      await saveByMode(uuid, payload, createCredential, updateCredential)
    } else if (activeTab.value === 'skills') {
      await saveByMode(uuid, payload, createSkill, updateSkill)
    } else if (activeTab.value === 'mcp') {
      await saveByMode(uuid, payload, createMcpServer, updateMcpServer)
    }
    showSuccess(t('lensAdmin.messages.saveSuccess'))
    if (showDrawer.value) {
      closeDrawer()
    } else {
      closeModal()
    }
    await load()
  } catch (error) {
    formError.value = resolveError(error, t('lensAdmin.messages.saveFailed'))
    showError(formError.value)
  } finally {
    saving.value = false
  }
}

async function saveByMode(uuid, payload, createFn, updateFn) {
  if (mode.value === 'create') {
    await createFn(payload)
  } else {
    await updateFn(uuid, payload)
  }
}

function buildPayload(tab) {
  if (tab === 'assistants') {
    const guideContent = (form.value.workspace_guide_overview || '').trim()
    return {
      name: form.value.name,
      slug: form.value.slug,
      lensnode_uuid: form.value.lensnode_uuid,
      selected_task: form.value.selected_task,
      selected_dirs: buildSelectedDirs(),
      agent_model_ref: form.value.agent_model_ref || null,
      agent_rounds: form.value.agent_rounds || 'balanced',
      max_concurrency: Number(form.value.max_concurrency) || 5,
      multimodal_model_ref: form.value.multimodal_model_ref || null,
      settings: buildAssistantSettings(),
      workspace_guide: {
        enabled: !!guideContent,
        content: guideContent
      },
      skill_bindings: (form.value.skill_uuids || []).map((uuid) => ({
        skill_uuid: uuid
      })),
      mcp_bindings: (form.value.mcp_uuids || []).map((uuid) => ({
        mcp_uuid: uuid
      })),
      status: form.value.status || 'active'
    }
  }
  if (tab === 'lensnodes') {
    return {
      name: form.value.name,
      workspace_path: form.value.workspace_path,
      protocol_version: form.value.protocol_version,
      agent_version: form.value.agent_version,
      labels: rowsToObject(form.value.labels_rows)
    }
  }
  if (tab === 'datasources') {
    const payload = {
      name: form.value.name,
      source_type: form.value.source_type,
      lensnode_uuid: form.value.lensnode_uuid,
      target_path: datasourceTargetPath(),
      config: buildDatasourceConfig(),
      sync_policy: buildDatasourceSyncPolicy(),
      status: form.value.status || 'active'
    }
    if (shouldUseDatasourceCredential()) {
      payload.credential_uuid = form.value.credential_uuid
    }
    return payload
  }
  if (tab === 'skills') {
    return {
      name: form.value.name,
      slug: form.value.slug,
      definition: form.value.definition_text,
      enabled: !!form.value.enabled
    }
  }
  if (tab === 'mcp') {
    return {
      name: form.value.name,
      transport: form.value.transport,
      endpoint: form.value.endpoint,
      config: rowsToObject(form.value.config_rows),
      enabled: !!form.value.enabled
    }
  }
  if (tab === 'credentials') {
    const payload = {
      name: form.value.name,
      provider: form.value.provider,
      auth_type: credentialFormAuthType.value
    }
    if (credentialFormAuthType.value === 'feishu_app') {
      if (form.value.app_id?.trim()) {
        payload.app_id = form.value.app_id.trim()
      }
      if (form.value.app_secret?.trim()) {
        payload.app_secret = form.value.app_secret.trim()
      }
    } else if (form.value.secret?.trim()) {
      payload.secret = form.value.secret.trim()
    }
    return payload
  }
  return {}
}

function buildAssistantSettings() {
  const settings = { ...(form.value.settings || {}) }
  const retrievalPolicy = {}
  const excludeExtensions = splitList(form.value.exclude_extensions_text)
  const excludeDirs = splitList(form.value.exclude_dirs_text)
  if (excludeExtensions.length) {
    retrievalPolicy.exclude_extensions = excludeExtensions
  }
  if (excludeDirs.length) {
    retrievalPolicy.exclude_dirs = excludeDirs
  }
  settings.retrieval_policy = retrievalPolicy
  if (form.value.pre_prompt?.trim()) {
    settings.pre_prompt = form.value.pre_prompt.trim()
  } else {
    delete settings.pre_prompt
  }
  if (form.value.post_prompt?.trim()) {
    settings.post_prompt = form.value.post_prompt.trim()
  } else {
    delete settings.post_prompt
  }
  return settings
}

function buildDatasourceConfig() {
  const config = { ...datasourceConfig.value }
  if (form.value.source_type === 'feishu') {
    config.doc_ids = String(config.doc_ids_text || '')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean)
    delete config.doc_ids_text
    if (config.sync_mode !== 'drive_folder') {
      delete config.folder_url
      delete config.folder_token
      delete config.recursive
      delete config.max_depth
    } else {
      delete config.document_url
      delete config.doc_ids
    }
    delete config.app_token
    delete config.app_id
    delete config.app_secret
  }
  return config
}

function buildDatasourceSyncPolicy() {
  if (syncPolicyMode.value === 'crontab') {
    return {
      mode: 'crontab',
      cron: String(syncCron.value || '').trim(),
      timezone: String(syncTimezone.value || '').trim() || 'UTC'
    }
  }
  return {
    mode: 'interval',
    interval_seconds: Math.max(1, Number(syncIntervalSeconds.value) || 3600)
  }
}

function datasourceTargetPath() {
  const relative = String(form.value.workspace_relative_path || '').trim()
  const workspace = datasourceWorkspaceRoot()
  return relative ? `${workspace}/${relative}` : ''
}

function workspaceRelativePath(targetPath, lensnodeUuid = null) {
  const value = String(targetPath || '').trim()
  const workspace = datasourceWorkspaceRoot(lensnodeUuid)
  if (value.startsWith(`${workspace}/`)) {
    return value.slice(workspace.length + 1)
  }
  return value
}

function datasourceWorkspaceRoot(lensnodeUuid = null) {
  const lensnode = lensnodeUuid
    ? lensnodes.value.find((node) => node.uuid === lensnodeUuid)
    : selectedDatasourceLensNode.value
  return String(lensnode?.workspace_path || '/workspace').replace(/\/+$/, '')
}

async function checkDatasourcePath() {
  if (!form.value.lensnode_uuid || !form.value.workspace_relative_path) return
  checkingDatasourcePath.value = true
  datasourcePathResult.value = null
  try {
    datasourcePathResult.value = await checkLensNodeDataSourcePath(
      form.value.lensnode_uuid,
      {
        target_path: datasourceTargetPath(),
        source_type: form.value.source_type,
        config: buildDatasourceConfig()
      }
    )
  } catch (error) {
    datasourcePathResult.value = {
      status: 'blocked',
      message: resolveError(error, t('lensAdmin.messages.loadFailed'))
    }
  } finally {
    checkingDatasourcePath.value = false
  }
}

function canSaveDatasource() {
  return datasourceConnectionResult.value?.status === 'success'
}

function resetDatasourceConnectionResult() {
  if (suppressDatasourceConnectionReset.value) {
    suppressDatasourceConnectionReset.value = false
    return
  }
  if (shouldKeepGitBranchConnectionResult()) {
    datasourceConnectionResult.value = {
      ...datasourceConnectionResult.value,
      details: {
        ...(datasourceConnectionResult.value?.details || {}),
        branch: datasourceConfig.value.branch
      }
    }
    return
  }
  datasourceConnectionResult.value = null
  datasourceConnectionBaseSignature.value = ''
}

async function testDatasourceConnection() {
  if (!form.value.lensnode_uuid) return
  testingDatasourceConnection.value = true
  datasourceConnectionResult.value = null
  try {
    const result = await testLensNodeDataSourceConnection(
      form.value.lensnode_uuid,
      {
        datasource_uuid: form.value.uuid || null,
        credential_uuid: shouldUseDatasourceCredential()
          ? form.value.credential_uuid
          : null,
        source_type: form.value.source_type,
        config: buildDatasourceConfig()
      }
    )
    applyDatasourceConnectionResult(result)
    datasourceConnectionResult.value = result
    datasourceConnectionBaseSignature.value = datasourceConnectionSignature(
      true
    )
  } catch (error) {
    datasourceConnectionResult.value = {
      status: 'failed',
      message: resolveError(error, t('lensAdmin.messages.loadFailed'))
    }
  } finally {
    testingDatasourceConnection.value = false
  }
}

function shouldUseDatasourceCredential() {
  if (!form.value.credential_uuid) {
    return false
  }
  if (form.value.source_type === 'git') {
    return datasourceConfig.value.auth_scheme === 'token'
  }
  return form.value.source_type === 'feishu'
}

async function createInlineCredential(payload) {
  try {
    const credential = await createCredential(payload)
    credentials.value = [credential, ...credentials.value]
    form.value.credential_uuid = credential.uuid
    showSuccess(t('lensAdmin.messages.saveSuccess'))
  } catch (error) {
    showError(resolveError(error, t('lensAdmin.messages.saveFailed')))
  }
}

function applyDatasourceConnectionResult(result) {
  if (form.value.source_type !== 'git' || result?.status !== 'success') {
    return
  }
  const branches = result?.details?.branches
  if (!Array.isArray(branches) || branches.length !== 1) {
    return
  }
  const branch = branches[0]
  if (datasourceConfig.value.branch !== branch) {
    suppressDatasourceConnectionReset.value = true
    datasourceConfig.value.branch = branch
  }
}

function shouldKeepGitBranchConnectionResult() {
  if (
    form.value.source_type !== 'git' ||
    datasourceConnectionResult.value?.status !== 'success'
  ) {
    return false
  }
  if (
    datasourceConnectionSignature(true) !==
    datasourceConnectionBaseSignature.value
  ) {
    return false
  }
  const branches = datasourceConnectionResult.value?.details?.branches
  return (
    Array.isArray(branches) &&
    branches.includes(datasourceConfig.value.branch)
  )
}

function datasourceConnectionSignature(ignoreBranch = false) {
  const config = buildDatasourceConfig()
  if (ignoreBranch) {
    delete config.branch
  }
  return JSON.stringify({
    lensnode_uuid: form.value.lensnode_uuid || '',
    source_type: form.value.source_type || '',
    config
  })
}

function buildSelectedDirs() {
  return selectedDirs().map((dir) => {
    const includePaths = String(dir.include_paths_text || '')
      .split('\n')
      .map((item) => item.trim())
      .filter(Boolean)
    if (!includePaths.length) {
      return { path: dir.path }
    }
    return {
      path: dir.path,
      retrieval_scope: { include_paths: includePaths }
    }
  })
}

async function remove(row) {
  try {
    if (activeTab.value === 'assistants') {
      await deleteAssistant(row.uuid)
    } else if (activeTab.value === 'lensnodes') {
      await deleteLensNode(row.uuid)
    } else if (activeTab.value === 'datasources') {
      await deleteDataSource(row.uuid)
    } else if (activeTab.value === 'credentials') {
      await deleteCredential(row.uuid)
    } else if (activeTab.value === 'skills') {
      await deleteSkill(row.uuid)
    } else if (activeTab.value === 'mcp') {
      await deleteMcpServer(row.uuid)
    }
    if (selectedDataSource.value?.uuid === row.uuid) {
      selectedDataSource.value = null
      showDatasourceDetailDrawer.value = false
    }
    showSuccess(t('lensAdmin.messages.deleteSuccess'))
    await load()
  } catch (error) {
    showError(resolveError(error, t('lensAdmin.messages.deleteFailed')))
  }
}

async function approve(row) {
  try {
    await approveLensNode(row.uuid)
    showSuccess(t('lensAdmin.messages.approveSuccess'))
    await load()
  } catch (error) {
    showError(resolveError(error, t('lensAdmin.messages.approveFailed')))
  }
}

async function issueToken(row) {
  try {
    const result = await issueLensNodeToken(row.uuid)
    const token = result?.token || result?.auth_token
    showSuccess(
      token
        ? t('lensAdmin.messages.tokenIssuedWithValue', { token })
        : t('lensAdmin.messages.tokenIssued')
    )
    await load()
  } catch (error) {
    showError(resolveError(error, t('lensAdmin.messages.tokenIssueFailed')))
  }
}

async function revokeToken(row) {
  try {
    await revokeLensNodeToken(row.uuid)
    showSuccess(t('lensAdmin.messages.tokenRevoked'))
    await load()
  } catch (error) {
    showError(resolveError(error, t('lensAdmin.messages.tokenRevokeFailed')))
  }
}

async function sync(row) {
  try {
    const result = await syncDataSource(row.uuid)
    const taskId = result?.task_id || ''
    showSuccess(
      taskId
        ? `${t('lensAdmin.messages.syncStarted')} (${taskId})`
        : t('lensAdmin.messages.syncStarted')
    )
    await load()
  } catch (error) {
    showError(resolveError(error, t('lensAdmin.messages.syncFailed')))
  }
}

async function cancelSync(row) {
  try {
    const result = await cancelDataSourceSync(row.uuid)
    const taskId = result?.task_id || row.current_sync?.task_id || ''
    showSuccess(
      taskId
        ? `${t('lensAdmin.messages.syncCancelled')} (${taskId})`
        : t('lensAdmin.messages.syncCancelled')
    )
    await load()
  } catch (error) {
    showError(resolveError(error, t('lensAdmin.messages.syncCancelFailed')))
  }
}

function resolveError(error, fallback) {
  return (
    error?.response?.data?.data?.detail ||
    error?.response?.data?.detail ||
    error?.message ||
    fallback
  )
}

watch(
  () => route.params.pathMatch,
  () => {
    parseRouteTab()
  },
  { immediate: true }
)

onMounted(load)
</script>

<style scoped>
.form-input {
  @apply w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}

.json-input {
  @apply w-full rounded-lg border border-line bg-surface px-3 py-2 font-mono text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}

.table-head {
  @apply border-b border-line px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-ink-500;
}

.table-cell {
  @apply px-4 py-4 text-sm text-ink-700;
}
</style>
