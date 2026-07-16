#!/bin/bash
# Shared blue/green helpers for scripts/install.sh and
# scripts/sourcelensctl.sh. Not meant to be run directly — source it after the
# caller has already set DEPLOY_PATH, cd'd into it, and defined log()/die()
# (this file intentionally doesn't define its own, or a lock helper — those are
# needed before this file is guaranteed to exist on a brand-new host, see
# install.sh's own bootstrap-ordering comment, so they stay duplicated inline in
# both scripts instead of being shared here).
#
# Installed/refreshed by install.sh like every other deploy asset (it's in
# install.sh's ASSETS list) — always present once install.sh has run at least
# once, which sourcelensctl.sh assumes.

GRACE_HEALTH_RETRIES="${GRACE_HEALTH_RETRIES:-40}"
GRACE_HEALTH_INTERVAL="${GRACE_HEALTH_INTERVAL:-3}"

# Image LABEL (stamped by the Dockerfiles from the APP_VERSION build arg) used
# by install.sh's version-skip check and by sourcelensctl.sh's rollback to
# recreate a color from the right image version.
VERSION_LABEL="com.oneprocloud.sourcelens.version"

# Read the release version stamped on a color's running API container, or empty
# if the container/label is absent.
color_image_version() {
    docker inspect \
        --format="{{index .Config.Labels \"${VERSION_LABEL}\"}}" \
        "sourcelens-api-$1" 2>/dev/null || echo ""
}

current_color() {
    cat "$DEPLOY_PATH/.active_color" 2>/dev/null || echo "blue"
}

other_color() {
    [ "$1" = "green" ] && echo "blue" || echo "green"
}

# Polls a container's /health endpoint. Returns 0 once healthy, 1 on timeout —
# never raises, callers decide what to do on failure.
wait_for_healthy() {
    local container="$1"
    local i
    for i in $(seq 1 "$GRACE_HEALTH_RETRIES"); do
        if docker exec "$container" \
            curl -fs http://127.0.0.1:8000/health >/dev/null 2>&1; then
            return 0
        fi
        sleep "$GRACE_HEALTH_INTERVAL"
    done
    return 1
}

# Flips nginx's upstream from color $1 to color $2, validates, reloads. Does not
# touch .active_color or start/stop any container — callers own that
# (install.sh's full deploy and sourcelensctl.sh's rollback both call this the
# same way, only what happens before/after it differs).
switch_traffic() {
    local from="$1" to="$2"
    log "Switching nginx upstream: ${from} -> ${to}"
    sed -i \
        -e "s/sourcelens-api-${from}/sourcelens-api-${to}/" \
        -e "s/sourcelens-ui-${from}/sourcelens-ui-${to}/" \
        "$DEPLOY_PATH/docker/nginx/conf.d/upstream.conf"
    docker exec sourcelens-nginx nginx -t
    docker exec sourcelens-nginx nginx -s reload
    log "Traffic switched to ${to}"
}
