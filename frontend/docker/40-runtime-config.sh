#!/bin/sh

set -eu

case "${TURNSTILE_ENABLED:-false}" in
  true | TRUE | True | 1 | yes | YES | Yes)
    turnstile_enabled=true
    ;;
  *)
    turnstile_enabled=false
    ;;
esac

site_key_base64="$(
  printf '%s' "${VITE_TURNSTILE_SITE_KEY:-}" | base64 | tr -d '\n'
)"

printf '%s\n' \
  "window.__SOURCELENS_CONFIG__ = {" \
  "  turnstileEnabled: ${turnstile_enabled}," \
  "  turnstileSiteKey: atob(\"${site_key_base64}\")" \
  "}" \
  > /usr/share/nginx/html/runtime-config.js
