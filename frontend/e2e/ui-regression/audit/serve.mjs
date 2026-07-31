#!/usr/bin/env node
/**
 * Tiny zero-dependency static server for the visual-audit HTML reports.
 * The audit report is a self-contained HTML file (screenshots inlined as
 * base64), so a plain file server is all that's needed to preview it.
 *
 *   npm run audit:serve                       # serves ./ on :9330
 *   AUDIT_DIR=/path PORT=8080 npm run audit:serve
 *
 * Lists the *.html reports at the root so you can pick one in the browser.
 */
import { createServer } from 'node:http'
import { readFile, readdir, stat } from 'node:fs/promises'
import { extname, join, normalize } from 'node:path'

const DIR = process.env.AUDIT_DIR || process.cwd()
const PORT = Number(process.env.PORT || 9330)

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.png': 'image/png',
  '.json': 'application/json; charset=utf-8',
  '.jsonl': 'text/plain; charset=utf-8'
}

async function listing() {
  const files = (await readdir(DIR)).filter((f) => f.endsWith('.html')).sort()
  const links = files
    .map((f) => `<li><a href="/${encodeURIComponent(f)}">${f}</a></li>`)
    .join('')
  return `<!doctype html><meta charset="utf-8"><title>Visual-audit reports</title>
<body style="font:15px/1.6 system-ui;margin:40px">
<h1>Visual-audit reports</h1>
<p>Serving <code>${DIR}</code></p>
<ul>${links || '<li>(no .html reports found)</li>'}</ul></body>`
}

createServer(async (req, res) => {
  try {
    const url = decodeURIComponent((req.url || '/').split('?')[0])
    if (url === '/' || url === '') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' })
      res.end(await listing())
      return
    }
    // Prevent path traversal: resolve within DIR only.
    const path = join(DIR, normalize(url).replace(/^(\.\.[/\\])+/, ''))
    if (!path.startsWith(DIR)) {
      res.writeHead(403)
      res.end('forbidden')
      return
    }
    await stat(path)
    res.writeHead(200, {
      'Content-Type': TYPES[extname(path)] || 'application/octet-stream'
    })
    res.end(await readFile(path))
  } catch {
    res.writeHead(404)
    res.end('not found')
  }
}).listen(PORT, '0.0.0.0', () => {
  console.log(`Visual-audit reports: http://localhost:${PORT}/  (dir: ${DIR})`)
  console.log(`On this host use its LAN/VPN IP, e.g. http://<ip>:${PORT}/`)
})
