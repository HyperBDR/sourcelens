import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = () =>
  readFile(
    new URL('../src/admin/pages/lens/RunObservation.vue', import.meta.url),
    'utf8'
  )

test('run detail title shows the selected task ID', async () => {
  const contents = await source()
  const titleIndex = contents.indexOf("t('lensRuns.detailTitle')")
  const taskIdIndex = contents.indexOf('data-testid="run-detail-id"')

  assert.ok(titleIndex >= 0)
  assert.ok(taskIdIndex > titleIndex)
  assert.match(contents.slice(taskIdIndex, taskIdIndex + 200), /selectedUuid/)
})

test('run task details omit individual model call rows', async () => {
  const contents = await source()

  assert.doesNotMatch(contents, /detail\.model_calls/)
  assert.doesNotMatch(
    contents,
    /v-for="\(call, index\) in detail\.model_calls"/
  )
})

test('run token summary separates totals, token metrics, and call counts', async () => {
  const contents = await source()

  assert.match(contents, /data-testid="run-token-summary"/)
  assert.match(contents, /lensRuns\.promptTokens/)
  assert.match(contents, /lensRuns\.completionTokens/)
  assert.match(contents, /lensRuns\.cachedTokens/)
  assert.match(contents, /lensRuns\.reasoningTokens/)
  assert.doesNotMatch(contents, /toLocaleString\(\) }}↑/)
})

test('run overview groups related fields and localizes analysis depth', async () => {
  const contents = await source()

  assert.match(contents, /data-testid="run-overview-summary"/)
  assert.match(contents, /data-testid="run-overview-execution"/)
  assert.match(contents, /data-testid="run-overview-timing"/)
  assert.match(contents, /data-testid="run-overview-resources"/)
  assert.match(contents, /data-testid="run-analysis-depth"/)
  assert.match(contents, /lensAdmin\.agentRounds/)
  assert.doesNotMatch(contents, /· \{\{ detail\.agent_rounds \}\}/)
})

test('run overview shows the models actually used by the run', async () => {
  const contents = await source()

  assert.match(contents, /data-testid="run-models-used"/)
  assert.match(contents, /lensRuns\.modelsUsed/)
  assert.match(contents, /detail\.models_used/)
})

test('run overview separates executor status from business outcome', async () => {
  const contents = await source()

  assert.match(contents, /detail\.executor_status/)
  assert.match(contents, /detail\.outcome/)
  assert.match(contents, /detail\.termination_detail/)
  assert.match(contents, /detail\.failure_summary/)
  assert.match(contents, /lensRuns\.executorStatus/)
  assert.match(contents, /lensRuns\.businessOutcome/)
})

test('run detail exposes the stable operations tabs in order', async () => {
  const contents = await source()
  const overviewIndex = contents.indexOf("activeDetailTab = 'overview'")
  const traceIndex = contents.indexOf("activeDetailTab = 'trace'")
  const resultsIndex = contents.indexOf("activeDetailTab = 'results'")
  const usageIndex = contents.indexOf("activeDetailTab = 'usage'")

  assert.match(contents, /data-testid="close-run-detail"/)
  assert.match(contents, /data-testid="run-diagnosis-tab"/)
  assert.match(contents, /data-testid="run-results-tab"/)
  assert.match(contents, /data-testid="run-files-tab"/)
  assert.match(contents, /data-testid="run-usage-tab"/)
  assert.ok(overviewIndex >= 0)
  assert.ok(traceIndex > overviewIndex)
  assert.ok(resultsIndex > traceIndex)
  assert.ok(usageIndex > resultsIndex)
  assert.doesNotMatch(contents, /activeDetailTab = 'progress'/)
  assert.doesNotMatch(contents, /activeDetailTab = 'evidence'/)
  assert.match(contents, /activeDetailTab = 'files'/)
  assert.match(contents, /activeDetailTab = 'diagnosis'/)
  assert.match(contents, /RunDiagnosisPanel/)
})

test('run detail tabs stay single-line and scroll on narrow screens', async () => {
  const contents = await source()

  assert.match(
    contents,
    /\.detail-tab\s*\{[^}]*shrink-0[^}]*whitespace-nowrap[^}]*\}/s
  )
})

test('diagnosis is available as a dedicated tab', async () => {
  const contents = await source()

  assert.match(contents, /data-testid="run-diagnosis-tab"/)
  assert.match(contents, /:active="activeDetailTab === 'diagnosis'"/)
  assert.match(contents, /@navigate="navigateFromEvidence"/)
})

test('operations center shows summary, node and model filters, and metrics', async () => {
  const contents = await source()

  assert.match(contents, /data-testid="run-status-summary"/)
  assert.match(contents, /filters\.lensnode/)
  assert.match(contents, /filters\.model/)
  assert.match(contents, /r\.tool_call_count/)
  assert.match(contents, /r\.retry_count/)
  assert.match(contents, /r\.budget_consumption/)
})

test('run actions use server-provided availability and confirmations', async () => {
  const contents = await source()

  assert.match(contents, /r\.available_actions\?\.cancel/)
  assert.match(contents, /r\.available_actions\?\.retry/)
  assert.match(contents, /detail\.available_actions\?\.resume/)
  assert.match(contents, /data-testid="run-action-confirm"/)
  assert.match(contents, /cancelAdminRun/)
  assert.match(contents, /retryAdminRun/)
  assert.match(contents, /resumeAdminRun/)
})

test('detail groups progress, evidence, artifacts, and diagnostics by task', async () => {
  const contents = await source()

  assert.match(contents, /data-testid="run-results-tab"/)
  assert.match(contents, /data-testid="run-results-content"/)
  assert.match(contents, /data-testid="run-usage-tab"/)
  assert.match(contents, /data-testid="run-live-progress"/)
  assert.match(contents, /data-testid="run-diagnosis-tab"/)
  assert.doesNotMatch(contents, /data-testid="run-evidence-tab"/)
  assert.match(contents, /data-testid="run-files-tab"/)
  assert.match(contents, /detail\.citations/)
  assert.match(contents, /detail\.output_files/)
  assert.match(
    contents,
    /\(detail\.citations \|\| \[\]\)\.length\s*\+\s*\(detail\.output_files \|\| \[\]\)\.length/
  )
  assert.match(contents, /citation\.supports/)
})

test('secondary run filters are disclosed on demand', async () => {
  const contents = await source()

  assert.match(contents, /data-testid="toggle-run-advanced-filters"/)
  assert.match(contents, /data-testid="run-advanced-filters"/)
  assert.match(contents, /advancedFiltersOpen/)
  assert.match(contents, /advancedFilterCount/)
  assert.match(contents, /filters\.lensnode/)
  assert.match(contents, /filters\.model/)
  assert.match(contents, /filters\.start_date/)
  assert.match(contents, /filters\.end_date/)
})

test('run statuses are localized consistently across list and detail', async () => {
  const contents = await source()

  assert.match(contents, /statusText\(r\.status\)/)
  assert.match(
    contents,
    /statusText\(detail\.executor_status \|\| detail\.status\)/
  )
})
