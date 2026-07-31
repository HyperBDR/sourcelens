import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  classifyAttachment,
  hasAttachmentErrorCode,
  validateAttachment
} from '../src/pages/lens/chatAttachments.js'

test('classifies supported images and office documents', () => {
  assert.equal(
    classifyAttachment({ name: 'screen.png', type: 'image/png' }),
    'image'
  )
  assert.equal(
    classifyAttachment({ name: 'Tender.PDF', type: 'application/pdf' }),
    'document'
  )
  assert.equal(
    classifyAttachment({ name: 'requirements.docx', type: '' }),
    'document'
  )
  assert.equal(
    classifyAttachment({ name: 'notes.txt', type: 'text/plain' }),
    ''
  )
})

test('enforces type, capability, size and shared count limits', () => {
  assert.deepEqual(
    validateAttachment(
      { name: 'tender.pdf', type: 'application/pdf', size: 25 * 1024 * 1024 },
      { acceptsImages: false, acceptsDocuments: true, currentCount: 0 }
    ),
    { kind: 'document', error: '' }
  )
  assert.equal(
    validateAttachment(
      {
        name: 'large.pdf',
        type: 'application/pdf',
        size: 25 * 1024 * 1024 + 1
      },
      { acceptsImages: false, acceptsDocuments: true, currentCount: 0 }
    ).error,
    'documentTooLarge'
  )
  assert.equal(
    validateAttachment(
      { name: 'screen.png', type: 'image/png', size: 100 },
      { acceptsImages: false, acceptsDocuments: true, currentCount: 0 }
    ).error,
    'imageUnavailable'
  )
  assert.equal(
    validateAttachment(
      { name: 'tender.pdf', type: 'application/pdf', size: 100 },
      { acceptsImages: true, acceptsDocuments: true, currentCount: 4 }
    ).error,
    'attachmentTooMany'
  )
})

test('preserves uploaded document metadata in optimistic messages', async () => {
  const source = await readFile(
    new URL('../src/pages/lens/Chat.vue', import.meta.url),
    'utf8'
  )
  const uploadStart = source.indexOf(
    'const result = await uploadAttachment(sessionUuid, file)'
  )
  const uploadEnd = source.indexOf("item.status = 'done'", uploadStart)
  const optimisticStart = source.indexOf(
    'attachments: pendingAttachments.map((item) => ({'
  )
  const optimisticEnd = source.indexOf('}))', optimisticStart)
  const uploadedMetadata = source.slice(uploadStart, uploadEnd)
  const optimisticMetadata = source.slice(optimisticStart, optimisticEnd)

  assert.match(uploadedMetadata, /item\.url = result\.url/)
  assert.match(uploadedMetadata, /item\.byte_size = result\.byte_size/)
  assert.match(optimisticMetadata, /uuid: item\.uuid/)
  assert.match(optimisticMetadata, /url: item\.url/)
  assert.match(optimisticMetadata, /byte_size: item\.byte_size/)
})

test('detects attachment errors in wrapped API responses', () => {
  const error = {
    response: {
      data: {
        code: 400,
        data: {
          non_field_errors: ['ATTACHMENT_NOT_FOUND']
        }
      }
    }
  }

  assert.equal(hasAttachmentErrorCode(error, 'ATTACHMENT_NOT_FOUND'), true)
  assert.equal(
    hasAttachmentErrorCode(error, 'ATTACHMENT_UNSUPPORTED_TYPE'),
    false
  )
})

test('does not restore missing or expired attachments', async () => {
  const source = await readFile(
    new URL('../src/pages/lens/Chat.vue', import.meta.url),
    'utf8'
  )
  const recoveryStart = source.indexOf('const requestRejected =')
  const recoveryEnd = source.indexOf("showError(t('lens.chat.submitFailed'))")
  const recovery = source.slice(recoveryStart, recoveryEnd)

  assert.match(recovery, /!runUuid/)
  assert.match(recovery, /err\?\.response\?\.status >= 400/)
  assert.match(recovery, /err\.response\.status < 500/)
  assert.match(recovery, /hasAttachmentErrorCode/)
  assert.match(recovery, /'ATTACHMENT_NOT_FOUND'/)
  assert.match(recovery, /!attachmentMissing/)
  assert.match(recovery, /pendingAttachments\.length\s+&&\s+requestRejected/)
})

test('deletes a document removed while its upload is in flight', async () => {
  const source = await readFile(
    new URL('../src/pages/lens/Chat.vue', import.meta.url),
    'utf8'
  )
  const uploadStart = source.indexOf(
    'const result = await uploadAttachment(sessionUuid, file)'
  )
  const uploadEnd = source.indexOf("item.status = 'done'", uploadStart)
  const uploadCompletion = source.slice(uploadStart, uploadEnd)

  assert.match(uploadCompletion, /!attachments\.value\.includes\(item\)/)
  assert.match(uploadCompletion, /removeAttachment\(item\)/)
})

test('requires task and LensNode capability before accepting documents', async () => {
  const source = await readFile(
    new URL('../src/pages/lens/Chat.vue', import.meta.url),
    'utf8'
  )
  const start = source.indexOf('const acceptsDocuments = computed(')
  const end = source.indexOf('const acceptsAttachments = computed(', start)
  const capabilityGate = source.slice(start, end)

  assert.match(capabilityGate, /selected_task !== 'general_chat'/)
  assert.match(capabilityGate, /supports_document_attachments === true/)
})
