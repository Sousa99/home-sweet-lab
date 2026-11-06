#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/kubectl-copy.sh
source "$script_dir/lib/kubectl-copy.sh"

namespace="${HASS_NAMESPACE:-home-assistant}"
pvc="${HASS_PVC:-home-assistant-config}"
source_dir="${HASS_BACKUPS_DIR:-/config/backups}"
dest="${HOME}/backups/home-sweet-lab/$(date +%Y%m%d-%H%M%S)"
helper_created=0
container=""
retries="${HASS_PULL_RETRIES:-5}"
chunk_size="${HASS_PULL_CHUNK_SIZE:-524288}"
work=""

usage() {
    cat <<'EOF'
Usage: pull-backups.sh [options]

Options:
  --dest DIR        Destination directory (default: ~/backups/home-sweet-lab/<timestamp>)
  --namespace NAME  Home Assistant namespace (default: home-assistant)
  --retries N       Attempts per chunk before failing (default: 5)
  -h, --help        Show this help

Environment:
  HASS_PULL_CHUNK_SIZE  Bytes per chunk (default: 524288)
  HASS_BACKUPS_DIR      Source directory inside the pod (default: /config/backups)

The script reads one chunk at a time and retries failed chunks, so a reset
exec/websocket stream does not abort the whole pull. Partial files are never
left in the destination.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dest) dest="$2"; shift 2 ;;
        --namespace) namespace="$2"; shift 2 ;;
        --retries) retries="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

if ! [[ "$retries" =~ ^[1-9][0-9]*$ ]]; then
    echo "--retries must be a positive integer" >&2
    exit 1
fi
if ! [[ "$chunk_size" =~ ^[1-9][0-9]*$ ]]; then
    echo "HASS_PULL_CHUNK_SIZE must be a positive integer" >&2
    exit 1
fi
if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl is required" >&2
    exit 1
fi

cleanup() {
    if [ -n "$work" ] && [ -d "$work" ]; then
        rm -rf "$work" 2>/dev/null || true
    fi
    if [ "$helper_created" -eq 1 ]; then
        kubectl -n "$namespace" delete pod ha-backup-pull --ignore-not-found >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

if command -v sha256sum >/dev/null 2>&1; then
    sum_cmd=(sha256sum)
else
    sum_cmd=(shasum -a 256)
fi

mkdir -p "$dest"
work="$(mktemp -d "$dest/.pull.XXXXXX")"

pod="$(kubectl -n "$namespace" get pod \
    -l app.kubernetes.io/name=home-assistant \
    --field-selector=status.phase=Running \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"

if [ -z "$pod" ]; then
    echo "No running Home Assistant pod; creating a helper pod."
    kubectl -n "$namespace" delete pod ha-backup-pull --ignore-not-found >/dev/null 2>&1 || true
    kubectl -n "$namespace" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: ha-backup-pull
spec:
  restartPolicy: Never
  automountServiceAccountToken: false
  containers:
    - name: pull
      image: alpine:3.20
      command: ["sh", "-c", "sleep 3600"]
      volumeMounts:
        - name: config
          mountPath: /config
          readOnly: true
  volumes:
    - name: config
      persistentVolumeClaim:
        claimName: $pvc
EOF
    helper_created=1
    kubectl -n "$namespace" wait --for=condition=Ready pod/ha-backup-pull --timeout=180s
    pod="ha-backup-pull"
    container="pull"
else
    container="home-assistant"
fi

exec_in_pod() {
    kubectl -n "$namespace" exec -c "$container" "$pod" -- "$@"
}

retry_exec() {
    local attempt=1
    while [ "$attempt" -le "$retries" ]; do
        if "$@"; then
            return 0
        fi
        attempt=$((attempt + 1))
        if [ "$attempt" -le "$retries" ]; then
            sleep 1
        fi
    done
    return 1
}

list_pod_files() {
    local out
    out="$(exec_in_pod sh -c '
        cd "$1" || exit 1
        find . -maxdepth 1 -type f | sed "s#^\./##"
    ' sh "$source_dir")" || return 1
    if [ -n "$out" ]; then
        printf '%s\n' "$out"
    fi
}

files="$(retry_exec list_pod_files | sort)" || {
    echo "Failed to list $namespace/$pod:$source_dir" >&2
    exit 1
}

if [ -z "$files" ]; then
    echo "No backups found in $namespace/$pvc:$source_dir" >&2
    exit 1
fi

count=0
while IFS= read -r file; do
    [ -n "$file" ] || continue
    echo "Pulling $file"
    if ! fetch_file_chunked "$namespace" "$pod" "$container" \
        "$source_dir/$file" "$work/$file" "$retries" "$chunk_size"; then
        echo "Failed to fetch $file after $retries attempts" >&2
        exit 1
    fi
    count=$((count + 1))
done <<< "$files"

while IFS= read -r file; do
    [ -n "$file" ] || continue
    mv "$work/$file" "$dest/$file"
done <<< "$files"

(
    cd "$dest"
    find . -maxdepth 1 -type f ! -name SHA256SUMS \
        -exec "${sum_cmd[@]}" {} + > SHA256SUMS
    "${sum_cmd[@]}" -c SHA256SUMS
)

echo "Pulled $count file(s) to $dest"
ls -lh "$dest"
