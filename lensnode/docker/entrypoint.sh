#!/usr/bin/env sh
set -eu

workspace="${LENSNODE_WORKSPACE_PATH:-/workspace}"
mkdir -p "$workspace"
export PYTHONPATH="/opt/lensnode${PYTHONPATH:+:$PYTHONPATH}"

if ! find "$workspace" -mindepth 1 -maxdepth 1 -type d | grep -q .; then
    mkdir -p "$workspace/default"
    printf '%s\n' '# LensNode Workspace' > "$workspace/default/README.md"
fi

exec "$@"
