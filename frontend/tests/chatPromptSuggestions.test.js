import assert from 'node:assert/strict'
import test from 'node:test'

import { promptSuggestionKeys } from '../src/pages/lens/chatPromptSuggestions.js'

test('uses code-analysis suggestions for code assistants', () => {
  assert.deepEqual(promptSuggestionKeys('code_analysis'), [
    'lens.chat.suggestions.codeArchitecture',
    'lens.chat.suggestions.codeFlow',
    'lens.chat.suggestions.codeRisks'
  ])
})

test('uses knowledge suggestions for knowledge assistants', () => {
  assert.deepEqual(promptSuggestionKeys('knowledge_qa'), [
    'lens.chat.suggestions.knowledgeSummary',
    'lens.chat.suggestions.knowledgeCompare',
    'lens.chat.suggestions.knowledgeActions'
  ])
})

test('falls back to general task suggestions for unknown assistants', () => {
  assert.deepEqual(promptSuggestionKeys('custom_task'), [
    'lens.chat.suggestions.generalCapabilities',
    'lens.chat.suggestions.generalAnalysis',
    'lens.chat.suggestions.generalPlan'
  ])
})
