export function supportsDatasourceArchiveUpload(lensnode) {
  return lensnode?.labels?.datasource_archive_upload === true
}

export function availableDatasourceLensNodes(lensnodes, sourceType) {
  return (lensnodes || []).filter(
    (node) =>
      node.status === 'online' &&
      node.enrollment_status === 'approved' &&
      !node.token_revoked &&
      (sourceType !== 'file' || supportsDatasourceArchiveUpload(node))
  )
}
