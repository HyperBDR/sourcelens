#!/bin/bash
# Day-2 operations for an already-installed sourcelens — status, restarting
# services, rolling back a blue/green switch. NOT for installing or upgrading to
# a new version — that's scripts/install.sh. Deliberately a separate script
# rather than more subcommands on install.sh: "install a new version" and
# "operate on what's already running" have different risk profiles and don't
# belong behind the same entrypoint.
#
# Installed/refreshed automatically every time install.sh runs (it's in
# install.sh's ASSETS list) — no separate curl needed once install.sh has run at
# least once on this host.
#
#   ./scripts/sourcelensctl.sh status            # active color + health + which containers are up
#   ./scripts/sourcelensctl.sh restart-workers   # graceful restart, no image pull, no color switch
#   ./scripts/sourcelensctl.sh rollback          # flip traffic back to the other color, no pull/build/migrate
set -euo pipefail

DEPLOY_PATH="${DEPLOY_PATH:-$(pwd)}"
cd "$DEPLOY_PATH"

log() { echo -e "\033[1;36m[sourcelensctl]\033[0m $*"; }
die() { echo -e "\033[1;31m[sourcelensctl] ERROR:\033[0m $*" >&2; exit 1; }

# --- Single-flight lock: shared with install.sh's lock file, so an ops command
# can't race a deploy (or another ops command) in flight.
acquire_deploy_lock() {
    local lock_file="/tmp/sourcelens-install.lock"
    local max_wait=300 waited=0
    while [ -f "$lock_file" ] && [ "$waited" -lt "$max_wait" ]; do
        log "install.sh (or another ops command) is running, waiting... (${waited}s)"
        sleep 5; waited=$((waited + 5))
    done
    echo "$$ $(date)" > "$lock_file"
    trap 'rm -f "'"$lock_file"'"' EXIT
}

[ -f "$DEPLOY_PATH/scripts/lib/deploy-common.sh" ] || die "scripts/lib/deploy-common.sh not found — run scripts/install.sh at least once first"
# shellcheck source=./lib/deploy-common.sh
source "$DEPLOY_PATH/scripts/lib/deploy-common.sh"

if [ -f "$DEPLOY_PATH/.env" ]; then
    set -a
    # shellcheck disable=SC1091
    source "$DEPLOY_PATH/.env"
    set +a
fi

cmd_status() {
    local color; color="$(current_color)"
    log "Active color: $color"
    echo
    docker compose ps \
        "sourcelens-api-${color}" "sourcelens-ui-${color}" \
        backend-worker backend-scheduler lensnode nginx \
        2>/dev/null || true
    echo
    if docker exec "sourcelens-api-${color}" \
        curl -fs http://127.0.0.1:8000/health >/dev/null 2>&1; then
        log "sourcelens-api-${color} (active): healthy"
    else
        log "sourcelens-api-${color} (active): NOT healthy"
    fi
}

cmd_restart_workers() {
    acquire_deploy_lock
    log "Restarting backend-worker / backend-scheduler / lensnode"
    log "(graceful: CELERY_TASK_ACKS_LATE + stop_grace_period mean in-flight"
    log "tasks finish before the old process exits, not a hard kill)"
    docker compose restart backend-worker backend-scheduler lensnode
    log "Done"
}

cmd_rollback() {
    acquire_deploy_lock
    local active target
    active="$(current_color)"
    target="$(other_color "$active")"
    log "Active color is ${active}; rolling back to ${target}"
    log "(no pull, no build, no migration — this only works if"
    log "sourcelens-api-${target}'s image is still present locally)"

    if ! docker compose --profile "$target" up -d \
        "sourcelens-api-${target}" "sourcelens-ui-${target}"; then
        die "Could not start sourcelens-api-${target}/sourcelens-ui-${target}. If that color's image was pruned, rollback isn't possible this way — redeploy the target version instead: ./scripts/install.sh <tag>"
    fi

    log "Waiting for sourcelens-api-${target} to report healthy..."
    if ! wait_for_healthy "sourcelens-api-${target}"; then
        docker compose --profile "$target" stop \
            "sourcelens-api-${target}" "sourcelens-ui-${target}"
        die "sourcelens-api-${target} never became healthy; rollback aborted, ${active} stays live"
    fi

    switch_traffic "$active" "$target"
    echo "$target" > "$DEPLOY_PATH/.active_color"

    log "Rolled back: active color is now ${target}."
    log "${active} was left running (not stopped) so you can inspect its logs."
    log "Once you've confirmed ${target} is good, retire it yourself:"
    log "  docker compose --profile ${active} stop sourcelens-api-${active} sourcelens-ui-${active}"
    log "  docker compose --profile ${active} rm -f sourcelens-api-${active} sourcelens-ui-${active}"
}

case "${1:-}" in
    status) cmd_status ;;
    restart-workers) cmd_restart_workers ;;
    rollback) cmd_rollback ;;
    *) die "Usage: $0 {status|restart-workers|rollback}" ;;
esac
