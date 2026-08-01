function sameAttachmentUuids(left, right) {
  return (
    left.length === right.length &&
    left.every((value, index) => value === right[index])
  )
}

function isSameSubmission(pending, candidate) {
  return Boolean(
    pending &&
    pending.sessionUuid === candidate.sessionUuid &&
    pending.question === candidate.question &&
    pending.retryOfRunUuid === candidate.retryOfRunUuid &&
    sameAttachmentUuids(pending.attachmentUuids, candidate.attachmentUuids)
  )
}

export function prepareRunSubmission({
  sessionUuid,
  question,
  attachmentUuids = [],
  retryDraft = null,
  pendingSubmission = null,
  answerLanguage = '',
  randomUUID = () => globalThis.crypto.randomUUID()
}) {
  const retryOfRunUuid =
    retryDraft?.question === question ? retryDraft.runUuid || '' : ''
  const candidate = {
    sessionUuid,
    question,
    attachmentUuids: [...attachmentUuids],
    retryOfRunUuid
  }
  const idempotencyKey = isSameSubmission(pendingSubmission, candidate)
    ? pendingSubmission.idempotencyKey
    : randomUUID()
  const submission = { ...candidate, idempotencyKey }
  const payload = {
    question,
    run_inline: false,
    enqueue: true,
    attachment_uuids: [...attachmentUuids],
    idempotency_key: idempotencyKey,
    answer_language: answerLanguage
  }
  if (retryOfRunUuid) {
    payload.retry_of_run_uuid = retryOfRunUuid
  }
  return { payload, submission }
}
