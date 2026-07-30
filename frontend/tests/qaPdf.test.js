import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

const source = (path) =>
  readFile(new URL(`../src/${path}`, import.meta.url), 'utf8')

test('PDF filename is derived from the conversation summary', async () => {
  const { buildQaPdfFilename } = await import('../src/utils/qaPdf.js')

  assert.equal(
    buildQaPdfFilename({
      summary: '  July orders: status / follow-up?  ',
      question: 'Fallback question'
    }),
    'July orders status follow-up.pdf'
  )
})

test('PDF filename falls back to the current question', async () => {
  const { buildQaPdfFilename } = await import('../src/utils/qaPdf.js')

  assert.equal(
    buildQaPdfFilename({ summary: '', question: '  Deployment overview  ' }),
    'Deployment overview.pdf'
  )
  assert.equal(
    buildQaPdfFilename({ summary: '', question: '' }),
    'SourceLens-conversation.pdf'
  )
})

test('content disposition filename is decoded and sanitized', async () => {
  const { filenameFromContentDisposition } =
    await import('../src/utils/qaPdf.js')

  assert.equal(
    filenameFromContentDisposition(
      "attachment; filename*=utf-8''%E4%B8%83%E6%9C%88%E8%AE%A2%E5%8D%95.pdf"
    ),
    '七月订单.pdf'
  )
  assert.equal(
    filenameFromContentDisposition('attachment; filename="report?.pdf"'),
    'report.pdf'
  )
})

test('Q&A exports fetch and download a PDF without printing', async () => {
  const [chat, publicQa, pdfUtility, lensApi] = await Promise.all([
    source('pages/lens/Chat.vue'),
    source('pages/lens/PublicQa.vue'),
    source('utils/qaPdf.js'),
    source('api/lens.js')
  ])

  assert.doesNotMatch(chat, /window\.print\(\)/)
  assert.doesNotMatch(publicQa, /window\.print\(\)/)
  assert.doesNotMatch(chat, /QaPrintView/)
  assert.doesNotMatch(publicQa, /QaPrintView/)
  assert.match(chat, /getRunPdf\(message\.run\)/)
  assert.match(publicQa, /getPublicQaPdf\(props\.token\)/)
  assert.match(chat, /downloadQaPdf/)
  assert.match(publicQa, /downloadQaPdf/)
  assert.match(chat, /beginActivity\(sessionUuid, activityId\)/)
  assert.match(chat, /endActivity\(sessionUuid, activityId\)/)
  assert.match(chat, /pdfGenerated/)
  assert.match(publicQa, /pdfGenerated/)
  assert.match(pdfUtility, /URL\.createObjectURL/)
  assert.match(pdfUtility, /link\.download = filename/)
  assert.match(pdfUtility, /link\.click\(\)/)
  assert.match(lensApi, /responseType:\s*'blob'/)
})

test('PDF download does not use screenshot or print libraries', async () => {
  const pdfUtility = await source('utils/qaPdf.js')

  assert.doesNotMatch(pdfUtility, /html2pdf|html2canvas|window\.print/)
})
