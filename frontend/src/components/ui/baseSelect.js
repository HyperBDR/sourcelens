export function applyModelModifiers(value, modifiers = {}) {
  if (!modifiers.number || typeof value !== 'string') return value

  const numberValue = Number.parseFloat(value)
  return Number.isNaN(numberValue) ? value : numberValue
}

function optionText(children) {
  if (children === null || children === undefined) return ''
  if (typeof children === 'string' || typeof children === 'number') {
    return String(children)
  }
  if (Array.isArray(children)) {
    return children.map((child) => optionText(child)).join('')
  }
  if (typeof children === 'object') return optionText(children.children)
  return ''
}

export function extractSelectOptions(nodes) {
  const options = []

  function visit(children) {
    for (const node of children || []) {
      if (node?.type === 'option') {
        const label = optionText(node.children).trim()
        const hasValue = Object.prototype.hasOwnProperty.call(
          node.props || {},
          'value'
        )
        options.push({
          key: node.key ?? `option-${options.length}`,
          label,
          value: hasValue ? node.props.value : label,
          disabled:
            node.props?.disabled !== undefined && node.props.disabled !== false
        })
      } else if (Array.isArray(node?.children)) {
        visit(node.children)
      }
    }
  }

  visit(nodes)
  return options
}

export function findNextEnabledOption(options, currentIndex, direction) {
  if (!options.length) return -1

  const step = direction < 0 ? -1 : 1
  let index = currentIndex

  for (let offset = 0; offset < options.length; offset += 1) {
    index = (index + step + options.length) % options.length
    if (!options[index]?.disabled) return index
  }

  return -1
}

export function findTypeaheadOption(options, query, currentIndex = -1) {
  const normalizedQuery = String(query || '')
    .trim()
    .toLocaleLowerCase()
  if (!normalizedQuery || !options.length) return -1

  for (let offset = 1; offset <= options.length; offset += 1) {
    const index = (currentIndex + offset + options.length) % options.length
    const option = options[index]
    if (
      !option?.disabled &&
      String(option.label).toLocaleLowerCase().startsWith(normalizedQuery)
    ) {
      return index
    }
  }

  return -1
}
