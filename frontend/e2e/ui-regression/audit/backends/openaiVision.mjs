/**
 * Standalone visual-judge backend (OpenAI-compatible vision).
 *
 * BYPASS by design: this file imports nothing from the app and touches no
 * business code. It reads its endpoint/key/model ONLY from env, so the secret
 * never lives in code or git and the audit stays a side-channel test tool.
 *
 * Required env:
 *   AUDIT_VISION_BASE_URL   OpenAI-compatible base, e.g. https://host/v1
 *   AUDIT_VISION_API_KEY    bearer key
 *   AUDIT_VISION_MODEL      a vision-capable model id
 *
 * Contract: default export (case) => { satisfied: boolean, note: string }
 * where case = { id, intent, screenshot }.
 */
import { readFileSync } from 'node:fs'

const BASE = process.env.AUDIT_VISION_BASE_URL
const KEY = process.env.AUDIT_VISION_API_KEY
const MODEL = process.env.AUDIT_VISION_MODEL

const NOTE_LANG = {
  en: 'Write the "note" value in English.',
  'zh-CN': 'Write the "note" value in Simplified Chinese (简体中文).'
}

function systemPrompt(lang) {
  return (
    'You are a UI/UX reviewer auditing a screenshot. Assess FIVE dimensions:\n' +
    '1. intent — does the screen match the declared test intent?\n' +
    '2. layout — is the layout sound for the given viewport? On MOBILE flag ' +
    'obvious problems: horizontal overflow, clipped/cut-off content, elements ' +
    'overlapping or cramped, text touching edges, controls too small/unreachable.\n' +
    '3. translation — is the visible text correct and consistent for the ' +
    'stated language? Flag untranslated keys, wrong-language text, or mixed ' +
    'languages.\n' +
    '4. style — visual consistency: alignment, spacing, obvious broken styling ' +
    'or unstyled elements.\n' +
    '5. clarity — is the screen understandable (labels/messages make sense)?\n\n' +
    'Reply with STRICT JSON and nothing else:\n' +
    '{"satisfied": boolean, "note": "<short overall reason>", ' +
    '"issues": ["<one problem>", ...]}\n' +
    '"satisfied" reflects DIMENSION 1 ONLY (does the screen match the intent). ' +
    'Set it false ONLY when the intent is genuinely not met. ' +
    '"issues" lists concrete problems from dimensions 2-5 (layout, translation, ' +
    'style, clarity) as WARNINGS — they do NOT flip satisfied to false. ' +
    'Empty array if none. Only report issues you are clearly confident about; ' +
    'do not nitpick. IMPORTANT: put NO double-quote characters inside strings. ' +
    (NOTE_LANG[lang] || NOTE_LANG.en)
  )
}

function dataUrl(path) {
  const b64 = readFileSync(path).toString('base64')
  return `data:image/png;base64,${b64}`
}

function parseVerdict(text) {
  const cleaned = String(text || '')
    .replace(/```json/gi, '')
    .replace(/```/g, '')
    .trim()
  // Try strict JSON first.
  const match = cleaned.match(/\{[\s\S]*\}/)
  try {
    const obj = JSON.parse(match ? match[0] : cleaned)
    return {
      satisfied: !!obj.satisfied,
      note: String(obj.note || ''),
      issues: Array.isArray(obj.issues) ? obj.issues.map(String) : []
    }
  } catch {
    // Robust fallback: models sometimes emit un-escaped quotes (e.g. full-width
    // 「」 or nested "..." inside a value), which breaks JSON.parse. Extract the
    // fields directly rather than failing the whole run.
    const satisfied = /"satisfied"\s*:\s*true/i.test(cleaned)
    const noteMatch = cleaned.match(/"note"\s*:\s*"([\s\S]*?)"\s*[,}]/)
    const note = noteMatch
      ? noteMatch[1]
      : cleaned.replace(/[{}]/g, '').slice(0, 300)
    const issuesMatch = cleaned.match(/"issues"\s*:\s*\[([\s\S]*?)\]/)
    const issues = issuesMatch
      ? issuesMatch[1]
          .split(/",\s*"/)
          .map((s) => s.replace(/^\s*"?|"?\s*$/g, ''))
          .filter(Boolean)
      : []
    return { satisfied, note, issues }
  }
}

export default async function judge(c) {
  if (!BASE || !KEY || !MODEL) {
    throw new Error(
      'Missing env: set AUDIT_VISION_BASE_URL / AUDIT_VISION_API_KEY / ' +
        'AUDIT_VISION_MODEL'
    )
  }
  const res = await fetch(`${BASE.replace(/\/$/, '')}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${KEY}`
    },
    body: JSON.stringify({
      model: MODEL,
      temperature: 0,
      messages: [
        { role: 'system', content: systemPrompt(c.noteLang || 'en') },
        {
          role: 'user',
          content: [
            {
              type: 'text',
              text:
                `Viewport: ${c.viewport || 'desktop'}` +
                (c.viewport === 'mobile'
                  ? ' (narrow phone screen — judge mobile layout strictly)'
                  : '') +
                `\nIntent: ${c.intent}`
            },
            { type: 'image_url', image_url: { url: dataUrl(c.screenshot) } }
          ]
        }
      ]
    })
  })
  if (!res.ok) {
    throw new Error(`vision backend HTTP ${res.status}`)
  }
  const data = await res.json()
  return parseVerdict(data?.choices?.[0]?.message?.content)
}
