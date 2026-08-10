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

test('run detail places diagnosis action before close and orders tabs', async () => {
  const contents = await source()
  const actionIndex = contents.indexOf('data-testid="generate-run-diagnosis"')
  const closeIndex = contents.indexOf('data-testid="close-run-detail"')
  const overviewIndex = contents.indexOf("activeDetailTab = 'overview'")
  const diagnosisIndex = contents.indexOf('data-testid="run-diagnosis-tab"')
  const traceIndex = contents.indexOf("activeDetailTab = 'trace'")
  const filesIndex = contents.indexOf("activeDetailTab = 'files'")

  assert.ok(actionIndex >= 0)
  assert.ok(closeIndex > actionIndex)
  assert.ok(overviewIndex >= 0)
  assert.ok(diagnosisIndex > overviewIndex)
  assert.ok(traceIndex > diagnosisIndex)
  assert.ok(filesIndex > traceIndex)
  assert.match(contents, /canDiagnoseRun/)
  assert.match(contents, /RunDiagnosisPanel/)
})

test('generate diagnosis switches tab and invokes the diagnosis panel', async () => {
  const contents = await source()

  assert.match(contents, /activeDetailTab\.value = 'diagnosis'/)
  assert.match(contents, /diagnosisPanel\.value\?\.generate\(\)/)
  assert.match(contents, /@navigate="navigateFromEvidence"/)
})
