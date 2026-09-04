function translatedText(pluginKey, path, fallback, t, te) {
  if (!pluginKey || !fallback) return fallback || ''
  const key = `lensAdmin.plugins.${pluginKey}.${path}`
  return te(key) ? t(key) : fallback
}

export function pluginDisplayName(plugin, t, te) {
  if (!plugin) return ''
  return translatedText(
    plugin.key,
    'displayName',
    plugin.display_name || plugin.key,
    t,
    te
  )
}

function localizeSchema(schema, schemaKey, pluginKey, t, te) {
  if (!schema?.properties) return schema
  const properties = Object.fromEntries(
    Object.entries(schema.properties).map(([fieldKey, field]) => [
      fieldKey,
      {
        ...field,
        title: translatedText(
          pluginKey,
          `${schemaKey}.${fieldKey}.title`,
          field.title || fieldKey,
          t,
          te
        ),
        description: translatedText(
          pluginKey,
          `${schemaKey}.${fieldKey}.description`,
          field.description,
          t,
          te
        )
      }
    ])
  )
  return { ...schema, properties }
}

export function localizePluginManifest(manifest, t, te) {
  if (!manifest) return manifest
  return {
    ...manifest,
    display_name: pluginDisplayName(manifest, t, te),
    description: translatedText(
      manifest.key,
      'description',
      manifest.description,
      t,
      te
    ),
    connection_schema: localizeSchema(
      manifest.connection_schema,
      'connectionFields',
      manifest.key,
      t,
      te
    ),
    datasource_schema: localizeSchema(
      manifest.datasource_schema,
      'datasourceFields',
      manifest.key,
      t,
      te
    )
  }
}
