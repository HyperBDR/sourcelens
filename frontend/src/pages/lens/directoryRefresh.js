function directoryPath(value) {
  return typeof value === 'string' ? value : value?.path || ''
}

export function directoryRefreshPaths(lensnode) {
  const workspacePath = lensnode?.workspace_path || '/workspace'
  const existingDirs = Array.isArray(lensnode?.available_dirs)
    ? lensnode.available_dirs
    : []
  const paths = [workspacePath, ...existingDirs.map(directoryPath)]

  return [...new Set(paths.filter(Boolean))]
}

function mergeDirectoryEntries(rootDirs, existingByPath, responseDirs) {
  return rootDirs.map((dir) => {
    const path = directoryPath(dir)
    const existing = existingByPath.get(path)
    const responseChildren = responseDirs?.[path]
    const children = Array.isArray(responseChildren)
      ? responseChildren
      : Array.isArray(dir?.children)
        ? dir.children
        : Array.isArray(existing?.children)
          ? existing.children
          : []

    if (typeof dir === 'string') {
      if (!children.length) return dir
      return { path, name: path.split('/').pop(), children }
    }

    return { ...dir, children }
  })
}

export function mergeRefreshedDirectories(existingDirs, result, workspacePath) {
  const previous = Array.isArray(existingDirs) ? existingDirs : []
  const existingByPath = new Map(
    previous.map((dir) => [directoryPath(dir), dir]).filter(([path]) => path)
  )
  const dirs = result?.dirs ?? result

  if (Array.isArray(dirs)) {
    return mergeDirectoryEntries(dirs, existingByPath, {})
  }
  if (!dirs || typeof dirs !== 'object') return []

  const rootDirs = dirs[workspacePath]
  if (!Array.isArray(rootDirs)) return []

  return mergeDirectoryEntries(rootDirs, existingByPath, dirs)
}
