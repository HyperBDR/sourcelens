<template>
  <BaseDrawer
    :show="show"
    :title="drawerTitle"
    :subtitle="drawerSubtitle"
    @close="$emit('close')"
  >
    <div class="mb-6 flex items-center">
      <template v-for="(step, i) in wizardStepsMeta" :key="step.key">
        <div class="flex flex-col items-center">
          <div
            class="flex h-8 w-8 items-center justify-center rounded-full border-2 text-sm font-medium transition-colors"
            :class="
              i + 1 < wizardStep
                ? 'border-brand-600 bg-brand-600 text-white'
                : i + 1 === wizardStep
                  ? 'border-brand-600 text-brand-600'
                  : 'border-line text-ink-400'
            "
          >
            <span v-if="i + 1 < wizardStep">✓</span>
            <span v-else>{{ i + 1 }}</span>
          </div>
          <span
            class="mt-1 text-xs"
            :class="
              i + 1 === wizardStep
                ? 'font-medium text-brand-600'
                : 'text-ink-400'
            "
          >
            {{ step.title }}
          </span>
        </div>
        <div
          v-if="i < wizardStepsMeta.length - 1"
          class="mb-4 mx-1 h-px flex-1 bg-line"
        />
      </template>
    </div>

    <div v-if="wizardStep === 1" class="space-y-5">
      <p class="text-sm text-ink-500">
        {{ t('lensAdmin.datasourceWizard.step1Desc') }}
      </p>
      <FormRow :label="t('lensAdmin.fields.name')" required>
        <input v-model="form.name" class="form-input" required />
      </FormRow>
      <FormRow :label="t('lensAdmin.fields.type')" required>
        <select
          v-model="form.source_type"
          class="form-input"
          @change="$emit('type-change')"
        >
          <option
            v-for="type in sourceTypes"
            :key="type.value"
            :value="type.value"
          >
            {{ type.label }}
          </option>
        </select>
        <p class="mt-1 text-xs text-ink-500">
          {{ selectedSourceTypeDescription }}
        </p>
      </FormRow>
      <FormRow :label="t('lensAdmin.fields.status')" required>
        <select v-model="form.status" class="form-input">
          <option value="active">{{ t('common.status.active') }}</option>
          <option value="disabled">{{ t('common.status.disabled') }}</option>
        </select>
      </FormRow>
    </div>

    <div v-else-if="wizardStep === 2" class="space-y-5">
      <p class="text-sm text-ink-500">
        {{ t('lensAdmin.datasourceWizard.step2Desc') }}
      </p>
      <FormRow :label="t('lensAdmin.fields.lensnode')" required>
        <select v-model="form.lensnode_uuid" class="form-input" required>
          <option value="">
            {{ t('lensAdmin.placeholders.selectLensNode') }}
          </option>
          <option
            v-for="node in onlineLensNodes"
            :key="node.uuid"
            :value="node.uuid"
          >
            {{ node.name }} · {{ node.workspace_path || '/workspace' }}
          </option>
        </select>
        <p class="mt-1 text-xs text-ink-500">
          {{ t('lensAdmin.datasourceWizard.onlineNodeHint') }}
        </p>
      </FormRow>
      <div
        v-if="!onlineLensNodes.length"
        class="rounded-md border border-warning-200 bg-warning-50 p-3 text-sm text-warning-800"
      >
        {{ t('lensAdmin.datasourceWizard.noOnlineNodes') }}
      </div>
    </div>

    <div v-else-if="wizardStep === 3" class="space-y-5">
      <p class="text-sm text-ink-500">
        {{ t('lensAdmin.datasourceWizard.step3Desc') }}
      </p>
      <template v-if="form.source_type === 'git'">
        <FormRow :label="t('lensAdmin.fields.repoUrl')" required>
          <input
            v-model="config.repo_url"
            class="form-input"
            placeholder="https://github.com/org/repo.git"
          />
          <p class="mt-1 text-xs text-ink-500">
            {{ t('lensAdmin.datasourceWizard.gitRepoHint') }}
          </p>
        </FormRow>
        <div class="grid gap-4 md:grid-cols-2">
          <FormRow :label="t('lensAdmin.fields.branch')">
            <select
              v-model="config.branch"
              class="form-input"
              :disabled="!gitBranchOptions.length"
            >
              <option value="">
                {{ t('lensAdmin.datasourceWizard.branchPlaceholder') }}
              </option>
              <option
                v-for="branch in gitBranchOptions"
                :key="branch"
                :value="branch"
              >
                {{ branch }}
              </option>
            </select>
          </FormRow>
          <FormRow :label="t('lensAdmin.fields.authScheme')" required>
            <select v-model="config.auth_scheme" class="form-input">
              <option value="none">
                {{ t('lensAdmin.datasourceWizard.authNone') }}
              </option>
              <option value="token">
                {{ t('lensAdmin.datasourceWizard.authToken') }}
              </option>
            </select>
          </FormRow>
        </div>
        <FormRow
          v-if="config.auth_scheme === 'token'"
          :label="t('lensAdmin.fields.credential')"
          required
        >
          <div class="flex flex-col gap-2">
            <div class="flex gap-2">
              <select v-model="form.credential_uuid" class="form-input">
                <option value="">
                  {{ t('lensAdmin.datasourceWizard.selectCredential') }}
                </option>
                <option
                  v-for="credential in filteredCredentials"
                  :key="credential.uuid"
                  :value="credential.uuid"
                >
                  {{ credential.name }}
                </option>
              </select>
              <BaseButton
                class="shrink-0"
                size="sm"
                variant="outline"
                :disabled="refreshingCredentials"
                :title="t('common.refresh')"
                @click="$emit('refresh-credentials')"
              >
                <RefreshCwIcon
                  class="h-4 w-4"
                  :class="{ 'animate-spin': refreshingCredentials }"
                />
                <span class="sr-only">{{ t('common.refresh') }}</span>
              </BaseButton>
            </div>
            <p class="text-xs text-ink-500">
              {{ t('lensAdmin.datasourceWizard.createCredentialHint') }}
              <a
                class="font-medium text-brand-600 hover:text-brand-700"
                href="/management/lens/resources/credentials"
                rel="noopener noreferrer"
                target="_blank"
              >
                {{ t('lensAdmin.datasourceWizard.createCredentialLink') }}
              </a>
            </p>
          </div>
        </FormRow>
      </template>
      <template v-else>
        <FormRow :label="t('lensAdmin.fields.syncScope')" required>
          <select v-model="config.sync_mode" class="form-input">
            <option value="document_list">
              {{ t('lensAdmin.datasourceWizard.feishuScopeDocuments') }}
            </option>
            <option value="drive_folder">
              {{ t('lensAdmin.datasourceWizard.feishuScopeDriveFolder') }}
            </option>
          </select>
        </FormRow>

        <FormRow :label="t('lensAdmin.fields.credential')" required>
          <div class="flex flex-col gap-2">
            <div class="flex gap-2">
              <select v-model="form.credential_uuid" class="form-input">
                <option value="">
                  {{ t('lensAdmin.datasourceWizard.selectFeishuCredential') }}
                </option>
                <option
                  v-for="credential in filteredCredentials"
                  :key="credential.uuid"
                  :value="credential.uuid"
                >
                  {{ credential.name }}
                </option>
              </select>
              <BaseButton
                class="shrink-0"
                size="sm"
                variant="outline"
                :disabled="refreshingCredentials"
                :title="t('common.refresh')"
                @click="$emit('refresh-credentials')"
              >
                <RefreshCwIcon
                  class="h-4 w-4"
                  :class="{ 'animate-spin': refreshingCredentials }"
                />
                <span class="sr-only">{{ t('common.refresh') }}</span>
              </BaseButton>
            </div>
            <p class="text-xs text-ink-500">
              {{ t('lensAdmin.datasourceWizard.createCredentialHint') }}
              <a
                class="font-medium text-brand-600 hover:text-brand-700"
                href="/management/lens/resources/credentials"
                rel="noopener noreferrer"
                target="_blank"
              >
                {{ t('lensAdmin.datasourceWizard.createCredentialLink') }}
              </a>
            </p>
          </div>
        </FormRow>

        <template v-if="config.sync_mode === 'drive_folder'">
          <FormRow :label="t('lensAdmin.fields.folderUrl')" required>
            <input
              v-model="config.folder_url"
              class="form-input"
              placeholder="https://xxx.feishu.cn/drive/folder/..."
            />
            <p class="mt-1 text-xs text-ink-500">
              {{ t('lensAdmin.datasourceWizard.feishuFolderHint') }}
            </p>
          </FormRow>
          <div class="grid gap-4 md:grid-cols-2">
            <FormRow :label="t('lensAdmin.fields.recursive')">
              <label
                class="inline-flex items-center gap-2 text-sm text-ink-600"
              >
                <input
                  v-model="config.recursive"
                  type="checkbox"
                  class="h-4 w-4 rounded border-line text-brand-600 focus:ring-brand-500"
                />
                {{ t('lensAdmin.datasourceWizard.recursiveHint') }}
              </label>
            </FormRow>
            <FormRow
              v-if="config.recursive"
              :label="t('lensAdmin.fields.maxDepth')"
            >
              <input
                v-model.number="config.max_depth"
                class="form-input"
                min="1"
                type="number"
              />
            </FormRow>
          </div>
        </template>

        <template v-else>
          <FormRow :label="t('lensAdmin.fields.documentUrl')">
            <input
              v-model="config.document_url"
              class="form-input"
              placeholder="https://xxx.feishu.cn/docx/..."
            />
            <p class="mt-1 text-xs text-ink-500">
              {{ t('lensAdmin.datasourceWizard.feishuUrlHint') }}
            </p>
          </FormRow>
          <FormRow :label="t('lensAdmin.fields.docIds')">
            <input
              v-model="config.doc_ids_text"
              class="form-input"
              :placeholder="t('lensAdmin.placeholders.docIds')"
            />
            <p class="mt-1 text-xs text-ink-500">
              {{ t('lensAdmin.datasourceWizard.feishuDocHint') }}
            </p>
          </FormRow>
        </template>
      </template>
      <div
        v-if="form.source_type === 'git' && gitBranchOptions.length"
        class="text-xs text-ink-500"
      >
        {{
          t('lensAdmin.datasourceWizard.branchCount', {
            count: gitBranchOptions.length
          })
        }}
      </div>
      <div class="flex items-center gap-2">
        <span
          v-if="form.source_type === 'git' && !gitBranchOptions.length"
          class="text-xs text-ink-500"
        >
          {{ t('lensAdmin.datasourceWizard.branchTestHint') }}
        </span>
      </div>
      <div
        v-if="connectionResult"
        class="rounded-md border p-3 text-sm"
        :class="
          connectionResult.status === 'success'
            ? 'border-success-200 bg-success-50 text-success-800'
            : 'border-danger-200 bg-danger-50 text-danger-800'
        "
      >
        {{ connectionResultMessage }}
      </div>
    </div>

    <div v-else-if="wizardStep === 4" class="space-y-5">
      <p class="text-sm text-ink-500">
        {{ t('lensAdmin.datasourceWizard.step4Desc') }}
      </p>
      <FormRow :label="t('lensAdmin.fields.targetPath')" required>
        <div class="space-y-3">
          <div
            class="rounded-md border border-line bg-surface-sunken px-3 py-2"
          >
            <div class="text-xs text-ink-500">
              {{ t('lensAdmin.datasourceWizard.selectedTargetPath') }}
            </div>
            <div class="mt-1 flex items-center gap-2">
              <div
                class="min-w-0 flex-1 break-all font-mono text-sm text-ink-900"
              >
                {{
                  form.workspace_relative_path ? targetPath : workspacePrefix
                }}
              </div>
              <LoaderCircleIcon
                v-if="checkingPath"
                class="h-4 w-4 shrink-0 animate-spin text-primary-600"
              />
              <CheckCircleIcon
                v-else-if="pathResult && pathResult.status !== 'blocked'"
                class="h-4 w-4 shrink-0 text-success-600"
              />
              <XCircleIcon
                v-else-if="pathResult && pathResult.status === 'blocked'"
                class="h-4 w-4 shrink-0 text-danger-600"
              />
            </div>
            <p
              v-if="pathResultMessage"
              class="mt-1 text-xs"
              :class="
                pathResult?.status === 'blocked'
                  ? 'text-danger-700'
                  : 'text-success-700'
              "
            >
              {{ pathResultMessage }}
            </p>
          </div>
          <div class="rounded-md border border-line bg-surface">
            <div
              class="flex items-center justify-between border-b border-line px-3 py-2"
            >
              <div class="text-sm font-medium text-ink-900">
                {{ workspaceRoot }}
              </div>
              <button
                class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded text-ink-500 hover:bg-surface-sunken hover:text-ink-900"
                type="button"
                :title="t('lensAdmin.datasourceWizard.createAtWorkspace')"
                @click="startCreateTargetDirectory('')"
              >
                <PlusIcon class="h-4 w-4" />
              </button>
            </div>
            <div class="max-h-64 overflow-y-auto p-2">
              <div
                v-if="creatingDirectoryParent === ''"
                class="flex gap-1 px-2 py-1"
              >
                <span class="h-7 w-7 shrink-0" />
                <input
                  v-model="newDirectoryName"
                  class="directory-name-input"
                  :placeholder="
                    t('lensAdmin.datasourceWizard.newDirPlaceholder')
                  "
                  @keyup.enter="selectNewTargetDirectory"
                />
                <button
                  class="directory-action-button text-success-600 hover:bg-success-50 hover:text-success-700 disabled:cursor-not-allowed disabled:opacity-40"
                  type="button"
                  :disabled="!canCreateTargetDirectory"
                  :title="t('common.confirm')"
                  @click="selectNewTargetDirectory"
                >
                  <CheckIcon class="h-4 w-4" />
                </button>
                <button
                  class="directory-action-button text-ink-500 hover:bg-surface-sunken hover:text-ink-900"
                  type="button"
                  :title="t('common.cancel')"
                  @click="cancelCreateTargetDirectory"
                >
                  <XIcon class="h-4 w-4" />
                </button>
              </div>
              <div
                v-if="!workspaceDirectoryTree.length"
                class="px-2 py-3 text-sm text-ink-500"
              >
                {{ t('lensAdmin.datasourceWizard.noWorkspaceDirs') }}
              </div>
              <div
                v-for="dir in workspaceDirectoryTree"
                :key="dir.path"
                class="space-y-1"
              >
                <div class="flex items-center gap-1">
                  <button
                    class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded text-ink-500 hover:bg-surface-sunken hover:text-ink-900"
                    type="button"
                    @click="toggleDirectoryExpanded(dir.relative)"
                  >
                    <component
                      :is="
                        isDirectoryExpanded(dir.relative)
                          ? ChevronDownIcon
                          : ChevronRightIcon
                      "
                      class="h-4 w-4"
                    />
                  </button>
                  <button
                    class="flex min-w-0 flex-1 items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-surface-sunken"
                    :class="directoryButtonClass(dir.relative)"
                    type="button"
                    @click="selectTargetDirectory(dir.relative)"
                  >
                    <component
                      :is="
                        isSelectedDirectory(dir.relative)
                          ? FolderOpenIcon
                          : FolderIcon
                      "
                      class="h-4 w-4 shrink-0"
                    />
                    <span class="truncate">{{ dir.name }}</span>
                  </button>
                  <button
                    class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded text-ink-500 hover:bg-surface-sunken hover:text-ink-900"
                    type="button"
                    :title="t('lensAdmin.datasourceWizard.createTargetDir')"
                    @click="startCreateTargetDirectory(dir.relative)"
                  >
                    <PlusIcon class="h-4 w-4" />
                  </button>
                </div>
                <div
                  v-if="creatingDirectoryParent === dir.relative"
                  class="ml-5 flex gap-1 border-l border-line pl-10"
                >
                  <input
                    v-model="newDirectoryName"
                    class="directory-name-input"
                    :placeholder="
                      t('lensAdmin.datasourceWizard.newDirPlaceholder')
                    "
                    @keyup.enter="selectNewTargetDirectory"
                  />
                  <button
                    class="directory-action-button text-success-600 hover:bg-success-50 hover:text-success-700 disabled:cursor-not-allowed disabled:opacity-40"
                    type="button"
                    :disabled="!canCreateTargetDirectory"
                    :title="t('common.confirm')"
                    @click="selectNewTargetDirectory"
                  >
                    <CheckIcon class="h-4 w-4" />
                  </button>
                  <button
                    class="directory-action-button text-ink-500 hover:bg-surface-sunken hover:text-ink-900"
                    type="button"
                    :title="t('common.cancel')"
                    @click="cancelCreateTargetDirectory"
                  >
                    <XIcon class="h-4 w-4" />
                  </button>
                </div>
                <div
                  v-if="isDirectoryExpanded(dir.relative)"
                  class="ml-5 space-y-1 border-l border-line pl-2"
                >
                  <div
                    v-if="!dir.children.length"
                    class="px-2 py-1.5 text-xs text-ink-400"
                  >
                    {{ t('lensAdmin.datasourceWizard.noChildDirs') }}
                  </div>
                  <div
                    v-for="child in dir.children"
                    :key="child.path"
                    class="space-y-1"
                  >
                    <div class="flex items-center gap-1">
                      <span class="h-7 w-7 shrink-0" />
                      <button
                        class="flex min-w-0 flex-1 items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-surface-sunken"
                        :class="directoryButtonClass(child.relative)"
                        type="button"
                        @click="selectTargetDirectory(child.relative)"
                      >
                        <component
                          :is="
                            isSelectedDirectory(child.relative)
                              ? FolderOpenIcon
                              : FolderIcon
                          "
                          class="h-4 w-4 shrink-0"
                        />
                        <span class="truncate">{{ child.name }}</span>
                      </button>
                      <button
                        class="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded text-ink-500 hover:bg-surface-sunken hover:text-ink-900"
                        type="button"
                        :title="t('lensAdmin.datasourceWizard.createTargetDir')"
                        @click="startCreateTargetDirectory(child.relative)"
                      >
                        <PlusIcon class="h-4 w-4" />
                      </button>
                    </div>
                    <div
                      v-if="creatingDirectoryParent === child.relative"
                      class="ml-8 flex gap-1"
                    >
                      <input
                        v-model="newDirectoryName"
                        class="directory-name-input"
                        :placeholder="
                          t('lensAdmin.datasourceWizard.newDirPlaceholder')
                        "
                        @keyup.enter="selectNewTargetDirectory"
                      />
                      <button
                        class="directory-action-button text-success-600 hover:bg-success-50 hover:text-success-700 disabled:cursor-not-allowed disabled:opacity-40"
                        type="button"
                        :disabled="!canCreateTargetDirectory"
                        :title="t('common.confirm')"
                        @click="selectNewTargetDirectory"
                      >
                        <CheckIcon class="h-4 w-4" />
                      </button>
                      <button
                        class="directory-action-button text-ink-500 hover:bg-surface-sunken hover:text-ink-900"
                        type="button"
                        :title="t('common.cancel')"
                        @click="cancelCreateTargetDirectory"
                      >
                        <XIcon class="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <p class="mt-1 text-xs text-ink-500">
          {{ t('lensAdmin.datasourceWizard.pathHint') }}
        </p>
      </FormRow>
      <FormRow :label="t('lensAdmin.fields.syncPolicy')" required>
        <select v-model="syncPolicyMode" class="form-input w-56">
          <option value="interval">
            {{ t('lensAdmin.datasourceWizard.syncPolicyInterval') }}
          </option>
          <option value="crontab">
            {{ t('lensAdmin.datasourceWizard.syncPolicyCrontab') }}
          </option>
        </select>
      </FormRow>
      <FormRow
        v-if="syncPolicyMode === 'interval'"
        :label="t('lensAdmin.fields.syncInterval')"
        required
      >
        <input
          v-model.number="syncIntervalSeconds"
          class="form-input w-40"
          min="60"
          type="number"
        />
        <p class="mt-1 text-xs text-ink-500">
          {{ t('lensAdmin.datasourceWizard.intervalHint') }}
        </p>
      </FormRow>
      <div v-else class="grid gap-4 md:grid-cols-2">
        <FormRow :label="t('lensAdmin.fields.cron')" required>
          <input
            v-model="syncCron"
            class="form-input font-mono"
            placeholder="0 2 * * *"
          />
        </FormRow>
        <FormRow :label="t('lensAdmin.fields.timezone')">
          <input
            v-model="syncTimezone"
            class="form-input"
            placeholder="Asia/Shanghai"
          />
        </FormRow>
      </div>
      <section v-if="form.source_type === 'feishu'" class="space-y-3 pt-1">
        <button
          class="flex w-full items-center justify-between text-left"
          type="button"
          @click="feishuAdvancedOpen = !feishuAdvancedOpen"
        >
          <span class="text-sm font-semibold text-ink-900">
            {{ t('lensAdmin.datasourceWizard.feishuAdvancedTitle') }}
          </span>
          <component
            :is="feishuAdvancedOpen ? ChevronDownIcon : ChevronRightIcon"
            class="h-4 w-4 text-ink-500"
          />
        </button>
        <div v-if="feishuAdvancedOpen" class="space-y-3">
          <label class="flex items-start gap-3">
            <input
              v-model="config.feishu_incremental"
              type="checkbox"
              class="mt-0.5 h-4 w-4 rounded border-line text-brand-600 focus:ring-brand-500"
            />
            <span>
              <span class="block text-sm font-medium text-ink-800">
                {{ t('lensAdmin.datasourceWizard.feishuIncrementalTitle') }}
              </span>
              <span class="mt-0.5 block text-xs leading-5 text-ink-500">
                {{ t('lensAdmin.datasourceWizard.feishuIncrementalHint') }}
              </span>
            </span>
          </label>
          <label class="flex items-start gap-3">
            <input
              v-model="config.feishu_delete_missing"
              type="checkbox"
              class="mt-0.5 h-4 w-4 rounded border-line text-brand-600 focus:ring-brand-500"
            />
            <span>
              <span class="block text-sm font-medium text-ink-800">
                {{ t('lensAdmin.datasourceWizard.feishuDeleteMissingTitle') }}
              </span>
              <span class="mt-0.5 block text-xs leading-5 text-ink-500">
                {{ t('lensAdmin.datasourceWizard.feishuDeleteMissingHint') }}
              </span>
            </span>
          </label>
        </div>
      </section>
    </div>

    <p v-if="formError" class="mt-4 text-sm text-danger-700">
      {{ formError }}
    </p>

    <template #footer>
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <BaseButton
            variant="outline"
            @click="wizardStep > 1 ? prevWizardStep() : $emit('close')"
          >
            {{
              wizardStep > 1 ? t('lensAdmin.wizard.back') : t('common.cancel')
            }}
          </BaseButton>
          <BaseButton
            v-if="wizardStep === 3"
            variant="outline"
            class="!border-primary-200 !bg-primary-50 !text-primary-700 hover:!border-primary-300 hover:!bg-primary-100"
            :disabled="!canTestConnection"
            :loading="testingConnection"
            @click="$emit('test-connection')"
          >
            {{ t('lensAdmin.datasourceWizard.testConnection') }}
          </BaseButton>
        </div>
        <div class="flex items-center gap-3">
          <span class="text-xs text-ink-400">
            {{ wizardStep }} / {{ WIZARD_STEP_COUNT }}
          </span>
          <BaseButton
            v-if="wizardStep < WIZARD_STEP_COUNT"
            variant="primary"
            :disabled="!canProceedWizard"
            @click="nextWizardStep"
          >
            {{ t('lensAdmin.wizard.next') }}
          </BaseButton>
          <BaseButton
            v-else
            variant="primary"
            :loading="saving"
            :disabled="
              !canProceedWizard ||
              pathResult?.status === 'blocked' ||
              connectionResult?.status !== 'success'
            "
            @click="$emit('save')"
          >
            {{
              mode === 'create'
                ? t('lensAdmin.wizard.finish')
                : t('common.save')
            }}
          </BaseButton>
        </div>
      </div>
    </template>
  </BaseDrawer>
</template>

<script setup>
import {
  CheckCircle as CheckCircleIcon,
  Check as CheckIcon,
  ChevronDown as ChevronDownIcon,
  ChevronRight as ChevronRightIcon,
  Folder as FolderIcon,
  FolderOpen as FolderOpenIcon,
  LoaderCircle as LoaderCircleIcon,
  Plus as PlusIcon,
  RefreshCw as RefreshCwIcon,
  X as XIcon,
  XCircle as XCircleIcon
} from '@lucide/vue'
import { computed, defineComponent, h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import BaseButton from '@/components/ui/BaseButton.vue'
import BaseDrawer from '@/components/ui/BaseDrawer.vue'

const props = defineProps({
  show: Boolean,
  mode: { type: String, default: 'create' },
  form: { type: Object, required: true },
  config: { type: Object, required: true },
  lensnodes: { type: Array, default: () => [] },
  credentials: { type: Array, default: () => [] },
  syncIntervalSeconds: { type: Number, default: 3600 },
  syncPolicyMode: { type: String, default: 'interval' },
  syncCron: { type: String, default: '0 2 * * *' },
  syncTimezone: { type: String, default: 'Asia/Shanghai' },
  pathResult: { type: Object, default: null },
  connectionResult: { type: Object, default: null },
  checkingPath: Boolean,
  testingConnection: Boolean,
  refreshingCredentials: Boolean,
  saving: Boolean,
  formError: { type: String, default: '' }
})

const emit = defineEmits([
  'close',
  'save',
  'type-change',
  'check-path',
  'test-connection',
  'connection-change',
  'refresh-credentials',
  'update:syncIntervalSeconds',
  'update:syncPolicyMode',
  'update:syncCron',
  'update:syncTimezone'
])

const { t } = useI18n()
const WIZARD_STEP_COUNT = 4
const wizardStep = ref(1)
const creatingDirectoryParent = ref(null)
const expandedDirectories = ref(new Set())
const newDirectoryName = ref('')
const feishuAdvancedOpen = ref(false)

const syncIntervalSeconds = computed({
  get() {
    return props.syncIntervalSeconds
  },
  set(value) {
    emit('update:syncIntervalSeconds', value)
  }
})

const syncPolicyMode = computed({
  get() {
    return props.syncPolicyMode
  },
  set(value) {
    emit('update:syncPolicyMode', value)
  }
})

const syncCron = computed({
  get() {
    return props.syncCron
  },
  set(value) {
    emit('update:syncCron', value)
  }
})

const syncTimezone = computed({
  get() {
    return props.syncTimezone
  },
  set(value) {
    emit('update:syncTimezone', value)
  }
})

const FormRow = defineComponent({
  props: {
    label: {
      type: String,
      required: true
    },
    required: {
      type: Boolean,
      default: false
    }
  },
  setup(rowProps, { slots }) {
    return () =>
      h('div', [
        h('label', { class: 'mb-1 block text-sm font-medium text-ink-700' }, [
          rowProps.label,
          rowProps.required
            ? h('span', { class: 'ml-0.5 text-danger-600' }, '*')
            : null
        ]),
        slots.default?.()
      ])
  }
})

const drawerTitle = computed(() =>
  props.mode === 'create'
    ? t('lensAdmin.datasourceWizard.createTitle')
    : t('lensAdmin.datasourceWizard.editTitle')
)

const drawerSubtitle = computed(() =>
  props.mode === 'edit' ? props.form.name || '' : ''
)

const sourceTypes = computed(() => [
  {
    value: 'git',
    label: 'Git',
    description: t('lensAdmin.datasourceWizard.gitDesc')
  },
  {
    value: 'feishu',
    label: t('lensAdmin.datasourceWizard.feishu'),
    description: t('lensAdmin.datasourceWizard.feishuDesc')
  }
])

const selectedSourceTypeDescription = computed(() => {
  const selected = sourceTypes.value.find(
    (type) => type.value === props.form.source_type
  )
  return selected?.description || ''
})

const wizardStepsMeta = computed(() => [
  { key: 'basic', title: t('lensAdmin.datasourceWizard.step1Title') },
  { key: 'node', title: t('lensAdmin.datasourceWizard.step2Title') },
  { key: 'connection', title: t('lensAdmin.datasourceWizard.step3Title') },
  { key: 'sync', title: t('lensAdmin.datasourceWizard.step4Title') }
])

const onlineLensNodes = computed(() =>
  props.lensnodes.filter(
    (node) =>
      node.status === 'online' &&
      node.enrollment_status === 'approved' &&
      !node.token_revoked
  )
)

const selectedLensNode = computed(() =>
  props.lensnodes.find((node) => node.uuid === props.form.lensnode_uuid)
)

const workspaceRoot = computed(() =>
  String(selectedLensNode.value?.workspace_path || '/workspace').replace(
    /\/+$/,
    ''
  )
)

const workspacePrefix = computed(() => `${workspaceRoot.value}/`)

const workspaceDirectoryTree = computed(() => {
  const dirs = Array.isArray(selectedLensNode.value?.available_dirs)
    ? selectedLensNode.value.available_dirs
    : []
  return dirs
    .map((dir) => normalizeDirectoryNode(dir))
    .filter((dir) => dir.relative)
})

const targetPath = computed(() => {
  const relative = String(props.form.workspace_relative_path || '').trim()
  return relative
    ? `${workspacePrefix.value}${relative}`
    : workspacePrefix.value
})

const canCreateTargetDirectory = computed(() =>
  isValidRelativeName(newDirectoryName.value)
)

const canTestConnection = computed(() => {
  if (!props.form.lensnode_uuid) {
    return false
  }
  if (props.form.source_type === 'git') {
    if (!props.config.repo_url?.trim()) {
      return false
    }
    return props.config.auth_scheme !== 'token' || !!props.form.credential_uuid
  }
  if (!hasFeishuCredential()) {
    return false
  }
  if (props.config.sync_mode === 'drive_folder') {
    return !!(
      props.config.folder_url?.trim() || props.config.folder_token?.trim()
    )
  }
  return !!(
    props.config.document_url?.trim() || props.config.doc_ids_text?.trim()
  )
})

const pathResultMessage = computed(() => {
  if (!props.pathResult) {
    return ''
  }
  const code = props.pathResult.message_code
  if (code) {
    const key = `lensAdmin.datasourceWizard.pathStatus.${code}`
    const translated = t(key)
    if (translated !== key) {
      return translated
    }
  }
  return props.pathResult.message || ''
})

const connectionResultMessage = computed(() => {
  if (!props.connectionResult) {
    return ''
  }
  const code = props.connectionResult.message_code
  if (code) {
    const key = `lensAdmin.datasourceWizard.connectionStatus.${code}`
    const translated = t(key)
    if (translated !== key) {
      const error = props.connectionResult.details?.error
      return error ? `${translated} ${error}` : translated
    }
  }
  return props.connectionResult.message || ''
})

const canProceedWizard = computed(() => {
  if (wizardStep.value === 1) {
    return !!props.form.name?.trim() && !!props.form.source_type
  }
  if (wizardStep.value === 2) {
    return !!props.form.lensnode_uuid
  }
  if (wizardStep.value === 3) {
    if (props.connectionResult?.status !== 'success') {
      return false
    }
    if (props.form.source_type === 'git') {
      return (
        gitBranchOptions.value.length > 0 &&
        gitBranchOptions.value.includes(props.config.branch)
      )
    }
    return true
  }
  if (!props.form.workspace_relative_path?.trim()) {
    return false
  }
  if (props.pathResult?.status === 'blocked' || !props.pathResult) {
    return false
  }
  if (syncPolicyMode.value === 'crontab') {
    return (
      String(syncCron.value || '')
        .trim()
        .split(/\s+/).length === 5
    )
  }
  return true
})

const gitBranchOptions = computed(() => {
  if (props.form.source_type !== 'git') {
    return []
  }
  const branches = props.connectionResult?.details?.branches
  return Array.isArray(branches) ? branches : []
})

const filteredCredentials = computed(() => {
  if (props.form.source_type === 'feishu') {
    return props.credentials.filter(
      (credential) => credential.auth_type === 'feishu_app'
    )
  }
  return props.credentials.filter(
    (credential) => credential.auth_type === 'https_token'
  )
})

function nextWizardStep() {
  if (wizardStep.value < WIZARD_STEP_COUNT) wizardStep.value++
}

function prevWizardStep() {
  if (wizardStep.value > 1) wizardStep.value--
}

function normalizeDirectoryNode(raw) {
  const path = typeof raw === 'string' ? raw : raw?.path || raw?.name || ''
  const name = typeof raw === 'string' ? path.split('/').pop() : raw?.name
  const relative = pathToWorkspaceRelative(path)
  const children = Array.isArray(raw?.children)
    ? raw.children
        .map((child) => normalizeDirectoryNode(child))
        .filter((child) => child.relative)
    : []
  return {
    path,
    name: name || relative || path,
    relative,
    children
  }
}

function pathToWorkspaceRelative(path) {
  const value = String(path || '').replace(/\/+$/, '')
  const workspace = workspaceRoot.value
  if (!value || value === workspace) {
    return ''
  }
  if (value.startsWith(`${workspace}/`)) {
    return value.slice(workspace.length + 1)
  }
  return value.replace(/^\/+/, '')
}

function isSelectedDirectory(relative) {
  return props.form.workspace_relative_path === relative
}

function directoryButtonClass(relative) {
  return isSelectedDirectory(relative)
    ? 'bg-brand-50 text-brand-700'
    : 'text-ink-700'
}

function isDirectoryExpanded(relative) {
  return expandedDirectories.value.has(relative)
}

function toggleDirectoryExpanded(relative) {
  const next = new Set(expandedDirectories.value)
  if (next.has(relative)) {
    next.delete(relative)
  } else {
    next.add(relative)
  }
  expandedDirectories.value = next
}

function selectTargetDirectory(relative) {
  props.form.workspace_relative_path = relative
  emit('check-path')
}

function isValidRelativeName(value) {
  const name = String(value || '').trim()
  return !!name && !name.includes('/') && !['.', '..'].includes(name)
}

function startCreateTargetDirectory(parent) {
  creatingDirectoryParent.value = parent
  newDirectoryName.value = ''
  if (parent) {
    expandedDirectories.value = new Set([
      ...expandedDirectories.value,
      parent.split('/')[0]
    ])
  }
}

function selectNewTargetDirectory() {
  if (!canCreateTargetDirectory.value) {
    return
  }
  const parent = String(creatingDirectoryParent.value || '').replace(/\/+$/, '')
  const name = String(newDirectoryName.value || '').trim()
  props.form.workspace_relative_path = parent ? `${parent}/${name}` : name
  newDirectoryName.value = ''
  creatingDirectoryParent.value = null
  emit('check-path')
}

function cancelCreateTargetDirectory() {
  newDirectoryName.value = ''
  creatingDirectoryParent.value = null
}

function hasFeishuCredential() {
  return !!props.form.credential_uuid
}

watch(
  () => props.show,
  (show) => {
    if (show) {
      wizardStep.value = 1
      creatingDirectoryParent.value = null
      expandedDirectories.value = new Set()
      newDirectoryName.value = ''
      feishuAdvancedOpen.value = false
    }
  }
)

watch(
  () => props.form.lensnode_uuid,
  () => {
    creatingDirectoryParent.value = null
    expandedDirectories.value = new Set()
    newDirectoryName.value = ''
  }
)

watch(
  () => [
    props.form.lensnode_uuid,
    props.form.source_type,
    props.form.credential_uuid,
    JSON.stringify(props.config || {})
  ],
  () => {
    emit('connection-change')
  }
)
</script>

<style scoped>
.form-input {
  @apply w-full rounded-lg border border-line bg-surface px-3 py-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}

.directory-action-button {
  @apply inline-flex h-7 w-7 shrink-0 items-center justify-center rounded transition-colors focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}

.directory-name-input {
  @apply h-7 min-w-0 flex-1 rounded border border-line bg-surface px-2 text-sm text-ink-900 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20;
}
</style>
