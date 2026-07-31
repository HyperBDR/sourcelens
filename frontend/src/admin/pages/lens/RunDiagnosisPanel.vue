<template>
  <div class="flex min-h-[32rem] flex-col bg-gray-50/60">
    <div class="flex-1 space-y-4 px-6 py-5">
      <BaseLoading v-if="loading && !latest" />

      <div
        v-else-if="loadError"
        class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700"
        role="alert"
      >
        {{ loadError }}
      </div>

      <section
        v-else-if="!latest"
        class="flex min-h-72 flex-col items-center justify-center rounded-xl border border-dashed border-gray-300 bg-white px-8 text-center"
        data-testid="diagnosis-empty"
      >
        <Sparkles :size="28" class="text-primary-500" aria-hidden="true" />
        <h3 class="mt-3 text-sm font-semibold text-gray-900">
          {{ t('lensRuns.diagnosisEmptyTitle') }}
        </h3>
        <p class="mt-1 max-w-md text-sm leading-6 text-gray-500">
          {{ t('lensRuns.diagnosisEmptyDescription') }}
        </p>
        <BaseButton
          class="mt-4"
          size="sm"
          :loading="generating"
          @click="generate"
        >
          {{ t('lensRuns.generateDiagnosis') }}
        </BaseButton>
      </section>

      <template v-else>
        <section
          v-if="isPending"
          class="rounded-xl border border-blue-200 bg-blue-50 p-5"
          aria-live="polite"
        >
          <div class="flex items-center gap-3">
            <span
              class="h-4 w-4 animate-spin rounded-full border-2 border-blue-200 border-t-blue-600"
              aria-hidden="true"
            />
            <div>
              <h3 class="text-sm font-semibold text-blue-900">
                {{ t('lensRuns.diagnosisRunning') }}
              </h3>
              <p class="mt-1 text-xs text-blue-700">
                {{ t('lensRuns.diagnosisRunningDescription') }}
              </p>
            </div>
          </div>
        </section>

        <section
          v-else-if="latest.status === 'failed'"
          class="rounded-xl border border-red-200 bg-red-50 p-5"
          role="alert"
        >
          <div class="flex items-start gap-3">
            <AlertTriangle
              :size="20"
              class="mt-0.5 text-red-600"
              aria-hidden="true"
            />
            <div class="flex-1">
              <h3 class="text-sm font-semibold text-red-900">
                {{ t('lensRuns.diagnosisFailed') }}
              </h3>
              <p class="mt-1 text-xs text-red-700">
                {{ diagnosisErrorLabel }}
              </p>
              <BaseButton
                class="mt-3"
                variant="outline"
                size="sm"
                :loading="generating"
                @click="generate"
              >
                {{ t('lensRuns.retryDiagnosis') }}
              </BaseButton>
            </div>
          </div>
        </section>

        <template v-else-if="latest.status === 'completed'">
          <section class="rounded-xl border border-gray-200 bg-white p-5">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p
                  class="text-xs font-medium uppercase tracking-wide text-gray-500"
                >
                  {{ t('lensRuns.diagnosisSummary') }}
                </p>
                <h3 class="mt-2 text-base font-semibold text-gray-900">
                  {{ latest.result.summary }}
                </h3>
              </div>
              <div class="flex items-center gap-2">
                <span :class="severityClass(latest.result.severity)">
                  {{ severityLabel(latest.result.severity) }}
                </span>
                <span
                  class="rounded-full bg-gray-100 px-2.5 py-1 text-xs text-gray-600"
                >
                  {{ confidenceText(latest.result.confidence) }}
                </span>
              </div>
            </div>
            <p class="mt-4 text-xs text-gray-500">
              {{ t('lensRuns.evidenceSnapshot') }}
              <span class="font-mono">{{
                shortHash(latest.evidence_hash)
              }}</span>
            </p>
          </section>

          <section
            v-if="latest.deterministic_findings?.length"
            class="rounded-xl border border-gray-200 bg-white p-5"
          >
            <h3 class="text-sm font-semibold text-gray-900">
              {{ t('lensRuns.deterministicChecks') }}
            </h3>
            <div class="mt-3 space-y-3">
              <article
                v-for="(finding, index) in latest.deterministic_findings"
                :key="`deterministic-${index}`"
                class="rounded-lg bg-gray-50 p-3"
              >
                <div class="flex items-start gap-2">
                  <CheckCircle2
                    :size="16"
                    class="mt-0.5 shrink-0 text-green-600"
                    aria-hidden="true"
                  />
                  <div class="min-w-0">
                    <p class="text-sm font-medium text-gray-900">
                      {{ finding.title }}
                    </p>
                    <p class="mt-1 text-sm leading-6 text-gray-600">
                      {{ finding.statement }}
                    </p>
                    <EvidenceLinks
                      :refs="finding.evidence_refs"
                      @navigate="navigateToEvidence"
                    />
                  </div>
                </div>
              </article>
            </div>
          </section>

          <section
            v-if="latest.result.findings?.length"
            class="rounded-xl border border-gray-200 bg-white p-5"
          >
            <h3 class="text-sm font-semibold text-gray-900">
              {{ t('lensRuns.findings') }}
            </h3>
            <div class="mt-3 space-y-3">
              <article
                v-for="(finding, index) in latest.result.findings"
                :key="`finding-${index}`"
                class="rounded-lg border border-gray-100 p-4"
              >
                <div class="flex items-center gap-2">
                  <span :class="kindClass(finding.kind)">
                    {{ kindLabel(finding.kind) }}
                  </span>
                  <span class="text-xs text-gray-400">
                    {{ confidenceText(finding.confidence) }}
                  </span>
                </div>
                <h4 class="mt-2 text-sm font-semibold text-gray-900">
                  {{ finding.title }}
                </h4>
                <p
                  class="mt-1 whitespace-pre-wrap text-sm leading-6 text-gray-600"
                >
                  {{ finding.statement }}
                </p>
                <EvidenceLinks
                  :refs="finding.evidence_refs"
                  @navigate="navigateToEvidence"
                />
              </article>
            </div>
          </section>

          <section
            v-if="latest.result.recommendations?.length"
            class="rounded-xl border border-emerald-200 bg-emerald-50/50 p-5"
          >
            <h3 class="text-sm font-semibold text-emerald-900">
              {{ t('lensRuns.recommendations') }}
            </h3>
            <div class="mt-3 space-y-3">
              <article
                v-for="(item, index) in latest.result.recommendations"
                :key="`recommendation-${index}`"
              >
                <p class="text-sm font-medium text-emerald-900">
                  {{ item.title }}
                </p>
                <p
                  class="mt-1 whitespace-pre-wrap text-sm leading-6 text-emerald-800"
                >
                  {{ item.action }}
                </p>
                <EvidenceLinks
                  :refs="item.evidence_refs"
                  @navigate="navigateToEvidence"
                />
              </article>
            </div>
          </section>

          <section
            v-if="latest.result.unknowns?.length"
            class="rounded-xl border border-amber-200 bg-amber-50/50 p-5"
          >
            <h3
              class="flex items-center gap-2 text-sm font-semibold text-amber-900"
            >
              <HelpCircle :size="16" aria-hidden="true" />
              {{ t('lensRuns.unknowns') }}
            </h3>
            <ul class="mt-3 space-y-2 text-sm leading-6 text-amber-900">
              <li
                v-for="(item, index) in latest.result.unknowns"
                :key="`unknown-${index}`"
              >
                {{ item.statement }}
                <EvidenceLinks
                  :refs="item.evidence_refs"
                  @navigate="navigateToEvidence"
                />
              </li>
            </ul>
          </section>

          <section
            v-if="latest.turns?.length"
            class="rounded-xl border border-gray-200 bg-white p-5"
            aria-live="polite"
          >
            <h3 class="text-sm font-semibold text-gray-900">
              {{ t('lensRuns.followUpConversation') }}
            </h3>
            <div class="mt-4 space-y-4">
              <article v-for="turn in latest.turns" :key="turn.uuid">
                <p
                  class="ml-auto max-w-[85%] rounded-xl bg-primary-600 px-4 py-3 text-sm text-white"
                >
                  {{ turn.question }}
                </p>
                <div
                  class="mt-2 max-w-[90%] rounded-xl bg-gray-100 px-4 py-3 text-sm leading-6 text-gray-700"
                >
                  <span v-if="turn.status === 'completed'">
                    {{ turn.answer }}
                  </span>
                  <span
                    v-else-if="turn.status === 'failed'"
                    class="text-red-700"
                  >
                    {{ t('lensRuns.followUpFailed') }}
                  </span>
                  <span v-else class="text-gray-500">
                    {{ t('lensRuns.followUpRunning') }}
                  </span>
                  <EvidenceLinks
                    :refs="turn.evidence_refs"
                    @navigate="navigateToEvidence"
                  />
                </div>
              </article>
            </div>
          </section>
        </template>
      </template>
    </div>

    <form
      v-if="latest?.status === 'completed'"
      class="sticky bottom-0 border-t border-gray-200 bg-white px-6 py-4 shadow-[0_-6px_18px_rgba(15,23,42,0.05)]"
      data-testid="diagnosis-follow-up"
      @submit.prevent="submitFollowUp"
    >
      <label
        for="run-diagnosis-question"
        class="text-xs font-medium text-gray-700"
      >
        {{ t('lensRuns.askAboutRun') }}
      </label>
      <div class="mt-2 flex gap-2">
        <input
          id="run-diagnosis-question"
          v-model="question"
          maxlength="2000"
          class="min-w-0 flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-primary-500 focus:outline-none focus:ring-2 focus:ring-primary-100"
          :placeholder="t('lensRuns.askAboutRunPlaceholder')"
          :disabled="submitting"
        />
        <BaseButton
          type="submit"
          :disabled="!question.trim()"
          :loading="submitting"
          :aria-label="t('lensRuns.sendFollowUp')"
        >
          <Send :size="16" aria-hidden="true" />
          <span class="sr-only">{{ t('lensRuns.sendFollowUp') }}</span>
        </BaseButton>
      </div>
      <p class="mt-2 text-xs text-gray-500">
        {{ t('lensRuns.followUpBoundary') }}
      </p>
    </form>
  </div>
</template>

<script setup>
import {
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Send,
  Sparkles
} from '@lucide/vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  createAdminRunDiagnosticTurn,
  generateAdminRunDiagnosis,
  getAdminRunDiagnostics
} from '@/api/lens'
import BaseButton from '@/components/ui/BaseButton.vue'
import BaseLoading from '@/components/ui/BaseLoading.vue'
import { extractErrorMessage } from '@/utils/api'

import EvidenceLinks from './RunDiagnosisEvidenceLinks.vue'

const props = defineProps({
  runUuid: { type: String, required: true },
  active: { type: Boolean, default: false }
})
const emit = defineEmits(['navigate'])
const { t } = useI18n()

const diagnostics = ref([])
const loading = ref(false)
const generating = ref(false)
const submitting = ref(false)
const loadError = ref('')
const question = ref('')
let pollTimer = null
let requestVersion = 0

const latest = computed(() => diagnostics.value[0] || null)
const isPending = computed(() =>
  ['queued', 'running'].includes(latest.value?.status)
)
const hasPendingTurn = computed(() =>
  (latest.value?.turns || []).some((turn) =>
    ['queued', 'running'].includes(turn.status)
  )
)
const diagnosisErrorLabel = computed(() => {
  const code = latest.value?.error_code
  if (!code) return t('lensRuns.diagnosisFailedDescription')
  const knownCodes = new Set([
    'MODEL_RESPONSE_INVALID',
    'INVALID_EVIDENCE_REFERENCE',
    'MODEL_CALL_FAILED'
  ])
  if (knownCodes.has(code)) return t(`lensRuns.diagnosisErrors.${code}`)
  return `${t('lensRuns.diagnosisFailedDescription')} (${code})`
})

async function load({ quiet = false } = {}) {
  if (!props.runUuid) return
  const version = ++requestVersion
  if (!quiet) loading.value = true
  try {
    const result = await getAdminRunDiagnostics(props.runUuid)
    if (version === requestVersion) {
      diagnostics.value = result
      loadError.value = ''
    }
  } catch (error) {
    if (!quiet && version === requestVersion) {
      loadError.value = extractErrorMessage(error, t('common.error'))
    }
  } finally {
    if (version === requestVersion) loading.value = false
  }
  if (version === requestVersion) schedulePoll()
}

async function generate() {
  if (!props.runUuid || generating.value) return
  const version = ++requestVersion
  generating.value = true
  loadError.value = ''
  try {
    const diagnostic = await generateAdminRunDiagnosis(props.runUuid)
    if (version === requestVersion) {
      diagnostics.value = [
        diagnostic,
        ...diagnostics.value.filter((item) => item.uuid !== diagnostic.uuid)
      ]
    }
  } catch (error) {
    if (version === requestVersion) {
      loadError.value = extractErrorMessage(error, t('common.error'))
    }
  } finally {
    if (version === requestVersion) generating.value = false
  }
  if (version === requestVersion) schedulePoll()
}

async function submitFollowUp() {
  const value = question.value.trim()
  if (!value || !latest.value || submitting.value) return
  const version = ++requestVersion
  submitting.value = true
  try {
    const turn = await createAdminRunDiagnosticTurn(
      props.runUuid,
      latest.value.uuid,
      value
    )
    if (version === requestVersion) {
      latest.value.turns = [
        ...(latest.value.turns || []).filter((item) => item.uuid !== turn.uuid),
        turn
      ]
      question.value = ''
      loadError.value = ''
    }
  } catch (error) {
    if (version === requestVersion) {
      loadError.value = extractErrorMessage(error, t('common.error'))
    }
  } finally {
    if (version === requestVersion) submitting.value = false
  }
  if (version === requestVersion) schedulePoll()
}

function schedulePoll() {
  clearPoll()
  if (!props.active || (!isPending.value && !hasPendingTurn.value)) return
  pollTimer = window.setTimeout(() => load({ quiet: true }), 1500)
}

function clearPoll() {
  if (pollTimer !== null) {
    window.clearTimeout(pollTimer)
    pollTimer = null
  }
}

function navigateToEvidence(evidenceRef) {
  emit('navigate', evidenceRef)
}

function shortHash(value) {
  return value ? value.slice(0, 12) : '-'
}

function confidenceText(value) {
  const confidence = Number(value)
  if (!Number.isFinite(confidence)) return t('lensRuns.confidenceUnknown')
  return t('lensRuns.confidence', { value: Math.round(confidence * 100) })
}

function severityLabel(value) {
  return t(`lensRuns.severity.${value}`, value || '-')
}

function kindLabel(value) {
  return t(`lensRuns.findingKind.${value}`, value || '-')
}

function severityClass(value) {
  const base = 'rounded-full px-2.5 py-1 text-xs font-semibold'
  const classes = {
    low: 'bg-green-100 text-green-800',
    medium: 'bg-amber-100 text-amber-800',
    high: 'bg-orange-100 text-orange-800',
    critical: 'bg-red-100 text-red-800'
  }
  return `${base} ${classes[value] || 'bg-gray-100 text-gray-700'}`
}

function kindClass(value) {
  const base = 'rounded-full px-2 py-0.5 text-xs font-semibold'
  return value === 'fact'
    ? `${base} bg-blue-100 text-blue-800`
    : `${base} bg-purple-100 text-purple-800`
}

watch(
  () => [props.runUuid, props.active],
  ([runUuid, active], previous) => {
    const previousRunUuid = previous?.[0]
    if (runUuid !== previousRunUuid) {
      requestVersion += 1
      diagnostics.value = []
      question.value = ''
      loadError.value = ''
    }
    if (active && runUuid) load()
    else clearPoll()
  },
  { immediate: true }
)

onBeforeUnmount(clearPoll)

defineExpose({ generate, load })
</script>
