#!/usr/bin/env bash

set -euo pipefail

usage() {
    cat <<'EOF'
Usage: scripts/sync_production_datasources.sh [options] [--apply]

Convert production legacy datasources to local Plugin datasources while
reusing the current local Connections. The default is a dry run.

Options:
  --source-host HOST          SSH destination, such as root@example.com
  --source-deploy-path PATH   Remote deployment path (default: /root/sourcelens)
  --source-container NAME     Remote API container; auto-detected when omitted
  --target-container NAME     Local API container (default: sourcelens-api-dev)
  --target-lensnode NAME      Local LensNode (default: local-dev-lensnode)
  --connection VALUE          Connection override: PLUGIN=NAME_OR_UUID
  --apply                     Commit changes; otherwise roll them back
  -h, --help                  Show this help
EOF
}

source_host="${SOURCELENS_SYNC_SOURCE_HOST:-}"
source_deploy_path="${SOURCELENS_SYNC_SOURCE_DEPLOY_PATH:-/root/sourcelens}"
source_container="${SOURCELENS_SYNC_SOURCE_CONTAINER:-}"
target_container="${SOURCELENS_SYNC_TARGET_CONTAINER:-sourcelens-api-dev}"
target_lensnode="${SOURCELENS_SYNC_TARGET_LENSNODE:-local-dev-lensnode}"
connections=("")
apply=0

while (($#)); do
    case "$1" in
        --source-host)
            source_host="$2"
            shift 2
            ;;
        --source-deploy-path)
            source_deploy_path="$2"
            shift 2
            ;;
        --source-container)
            source_container="$2"
            shift 2
            ;;
        --target-container)
            target_container="$2"
            shift 2
            ;;
        --target-lensnode)
            target_lensnode="$2"
            shift 2
            ;;
        --connection)
            connections+=("$2")
            shift 2
            ;;
        --apply)
            apply=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            usage >&2
            exit 2
            ;;
    esac
done

if [[ -z "$source_host" ]]; then
    echo "--source-host or SOURCELENS_SYNC_SOURCE_HOST is required" >&2
    exit 2
fi
if [[ ! "$source_host" =~ ^[A-Za-z0-9._@:-]+$ ]]; then
    echo "source host contains unsupported characters" >&2
    exit 2
fi
if [[ ! "$source_deploy_path" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
    echo "source deployment path contains unsupported characters" >&2
    exit 2
fi
if [[ ! "$target_container" =~ ^[A-Za-z0-9_.-]+-dev$ ]]; then
    echo "target container must use the -dev suffix" >&2
    exit 2
fi

if [[ -z "$source_container" ]]; then
    source_container="$({
        ssh -o BatchMode=yes "$source_host" \
            "cd '$source_deploy_path' && color=\$(cat .active_color) && printf 'sourcelens-api-%s' \"\$color\""
    })"
fi
if [[ ! "$source_container" =~ ^[A-Za-z0-9_.-]+$ ]]; then
    echo "source container name contains unsupported characters" >&2
    exit 2
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exporter="$script_dir/export_legacy_plugin_datasource_snapshot.py"
import_args=(
    python manage.py sync_plugin_datasource_snapshot
    --input -
    --lensnode "$target_lensnode"
)
for ((index = 1; index < ${#connections[@]}; index++)); do
    import_args+=(--connection "${connections[$index]}")
done
if ((apply)); then
    import_args+=(--apply)
fi

ssh -o BatchMode=yes "$source_host" \
    "docker exec -i '$source_container' python manage.py shell -c 'exec(__import__(\"sys\").stdin.read())'" \
    < "$exporter" |
    docker exec -i \
        -e SOURCELENS_ALLOW_DATASOURCE_IMPORT=true \
        "$target_container" "${import_args[@]}"
