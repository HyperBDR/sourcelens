export function formatDateTime(value) {
  if (!value) {
    return '未记录'
  }

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(new Date(value))
}

export function compactUuid(value) {
  if (!value) {
    return '-'
  }

  return `${String(value).slice(0, 8)}...${String(value).slice(-6)}`
}

export function modelCheckStatus(assistant) {
  const check = assistant?.settings?._model_check || {}
  const fields = [
    'preprocess_model_ref',
    'postprocess_model_ref',
    'agent_model_ref',
    'multimodal_model_ref'
  ]

  if (fields.some((field) => check[field]?.status === 'error')) {
    return 'failed'
  }
  if (fields.some((field) => check[field]?.status === 'ok')) {
    return 'success'
  }
  return 'pending'
}
