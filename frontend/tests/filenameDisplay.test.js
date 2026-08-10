import test from 'node:test'
import assert from 'node:assert/strict'

import { compactFilename } from '../src/pages/lens/filenameDisplay.js'

test('keeps short filenames unchanged', () => {
  assert.equal(compactFilename('report.pdf'), 'report.pdf')
})

test('middle-ellipsizes long filenames while preserving the extension', () => {
  const filenames = [
    ['Git面试高频问题+简洁答案（适配Word）.pdf', '.pdf'],
    ['Git面试高频问题+简洁答案（适配Word）.docx', '.docx'],
    ['Git面试高频问题+简洁答案（适配Word）.pptx', '.pptx'],
    ['Git面试高频问题+简洁答案（适配Word）.xlsx', '.xlsx']
  ]

  for (const [filename, extension] of filenames) {
    const compacted = compactFilename(filename)
    assert.match(compacted, /\.{3}/)
    assert.ok(compacted.endsWith(extension))
    assert.ok(compacted.length <= 22)
  }

  assert.equal(
    compactFilename('Git面试高频问题+简洁答案（适配Word）.pdf'),
    'Git面试高频...（适配Word）.pdf'
  )
})

test('handles filenames without an extension', () => {
  assert.equal(
    compactFilename('a-very-long-document-name-for-mobile'),
    'a-very-l...-for-mobile'
  )
})

test('handles empty filenames', () => {
  assert.equal(compactFilename(''), '')
})
