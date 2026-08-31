import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test from 'node:test'

import {
  attachmentUploadError,
  classifyAttachment,
  createOversizedTextFile,
  hasAttachmentErrorCode,
  MAX_DIRECT_MESSAGE_CHARS,
  MAX_IMAGE_ASPECT_RATIO,
  MAX_IMAGE_PIXELS,
  readImageDimensions,
  validateImageDimensions,
  validateAttachment
} from '../src/pages/lens/chatAttachments.js'

test('classifies supported images, office documents and text files', () => {
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
    'document'
  )
  assert.equal(
    classifyAttachment({ name: 'investigation.MD', type: 'text/markdown' }),
    'document'
  )
})

test('converts oversized composer text into a UTF-8 text file', async () => {
  const text = `incident\n${'证据'.repeat(MAX_DIRECT_MESSAGE_CHARS)}`

  const file = createOversizedTextFile(text, new Date('2026-08-24T05:30:45Z'))

  assert.equal(file.name, 'long-input-20260824-053045.txt')
  assert.equal(file.type, 'text/plain')
  assert.equal(await file.text(), text)
  assert.equal(createOversizedTextFile('short input'), null)
})

test('uploads oversized composer text before submitting the Run', async () => {
  const source = await readFile(
    new URL('../src/pages/lens/Chat.vue', import.meta.url),
    'utf8'
  )
  const submitStart = source.indexOf('async function submit()')
  const submitEnd = source.indexOf('async function cancel()', submitStart)
  const submitFlow = source.slice(submitStart, submitEnd)
  const createFile = submitFlow.indexOf('createOversizedTextFile(')
  const uploadFile = submitFlow.indexOf('await addAttachment(oversizedFile)')
  const createRun = submitFlow.indexOf('await createRun(')

  assert.ok(createFile >= 0)
  assert.ok(createFile < uploadFile)
  assert.ok(uploadFile < createRun)
  assert.match(submitFlow, /question\.value = draftTextAtSubmit/)
  assert.match(submitFlow, /oversizedTextAttached/)
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

test('enforces image pixel and aspect-ratio boundaries', () => {
  assert.equal(validateImageDimensions(2500, MAX_IMAGE_PIXELS / 2500), '')
  assert.equal(validateImageDimensions(1000 * MAX_IMAGE_ASPECT_RATIO, 1000), '')
  assert.equal(validateImageDimensions(2501, 2000), 'imageDimensionsTooLarge')
  assert.equal(
    validateImageDimensions(1000, 1000 * MAX_IMAGE_ASPECT_RATIO + 1),
    'imageAspectUnsupported'
  )
})

test('maps backend dimension errors to actionable upload messages', () => {
  const apiError = (code) => ({ response: { data: { errors: [code] } } })

  assert.equal(
    attachmentUploadError(apiError('ATTACHMENT_DIMENSIONS_TOO_LARGE')),
    'imageDimensionsTooLarge'
  )
  assert.equal(
    attachmentUploadError(apiError('ATTACHMENT_ASPECT_UNSUPPORTED')),
    'imageAspectUnsupported'
  )
  assert.equal(
    attachmentUploadError(new Error('network')),
    'attachmentUploadFailed'
  )
})

test('checks browser image dimensions before uploading', async () => {
  const source = await readFile(
    new URL('../src/pages/lens/Chat.vue', import.meta.url),
    'utf8'
  )
  const dimensionCheck = source.indexOf('await readImageDimensions(file)')
  const uploadStart = source.indexOf(
    'const result = await uploadAttachment(sessionUuid, file)'
  )

  assert.notEqual(dimensionCheck, -1)
  assert.ok(dimensionCheck < uploadStart)
})

test('releases the browser image URL after reading dimensions', async (t) => {
  const originalImage = globalThis.Image
  const originalCreateObjectURL = URL.createObjectURL
  const originalRevokeObjectURL = URL.revokeObjectURL
  const revoked = []

  t.after(() => {
    globalThis.Image = originalImage
    URL.createObjectURL = originalCreateObjectURL
    URL.revokeObjectURL = originalRevokeObjectURL
  })
  URL.createObjectURL = () => 'blob:dimensions-success'
  URL.revokeObjectURL = (url) => revoked.push(url)
  globalThis.Image = class {
    set src(_value) {
      this.naturalWidth = 1200
      this.naturalHeight = 800
      queueMicrotask(() => this.onload())
    }
  }

  const dimensions = await readImageDimensions({ name: 'screen.png' })

  assert.deepEqual(dimensions, { width: 1200, height: 800 })
  assert.deepEqual(revoked, ['blob:dimensions-success'])
})

test('releases the browser image URL when dimensions fail', async (t) => {
  const originalImage = globalThis.Image
  const originalCreateObjectURL = URL.createObjectURL
  const originalRevokeObjectURL = URL.revokeObjectURL
  const revoked = []

  t.after(() => {
    globalThis.Image = originalImage
    URL.createObjectURL = originalCreateObjectURL
    URL.revokeObjectURL = originalRevokeObjectURL
  })
  URL.createObjectURL = () => 'blob:dimensions-error'
  URL.revokeObjectURL = (url) => revoked.push(url)
  globalThis.Image = class {
    set src(_value) {
      queueMicrotask(() => this.onerror())
    }
  }

  await assert.rejects(
    readImageDimensions({ name: 'broken.png' }),
    /IMAGE_DIMENSIONS_UNAVAILABLE/
  )
  assert.deepEqual(revoked, ['blob:dimensions-error'])
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
  assert.match(recovery, /retryableAttachments\.length\s+&&\s+requestRejected/)
  assert.match(recovery, /item !== oversizedAttachment/)
  assert.match(recovery, /deleteAttachment\(oversizedAttachment\.uuid\)/)
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

test('uses the LensNode capability for every assistant type', async () => {
  const source = await readFile(
    new URL('../src/pages/lens/Chat.vue', import.meta.url),
    'utf8'
  )
  const start = source.indexOf('const acceptsDocuments = computed(')
  const end = source.indexOf('const acceptsAttachments = computed(', start)
  const capabilityGate = source.slice(start, end)

  assert.match(capabilityGate, /supports_document_attachments === true/)
  assert.doesNotMatch(capabilityGate, /selected_task/)
})

test('Smart Collaboration aggregates document capability from participants', async () => {
  const source = await readFile(
    new URL('../src/pages/lens/Chat.vue', import.meta.url),
    'utf8'
  )
  const start = source.indexOf('const acceptsDocuments = computed(')
  const end = source.indexOf('const acceptsAttachments = computed(', start)
  const capabilityGate = source.slice(start, end)

  assert.match(capabilityGate, /isSmartCollaborationConversation\.value/)
  assert.match(capabilityGate, /participants\.every/)
  assert.match(capabilityGate, /supports_document_attachments === true/)
})
