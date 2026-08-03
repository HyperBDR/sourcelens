export function applyModelModifiers(value, modifiers = {}) {
  if (!modifiers.number || typeof value !== 'string') return value

  const numberValue = Number.parseFloat(value)
  return Number.isNaN(numberValue) ? value : numberValue
}
