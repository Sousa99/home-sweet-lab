#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/kubectl-copy.sh
source "$script_dir/lib/kubectl-copy.sh"

namespace="${HASS_NAMESPACE:-home-assistant}"
pvc="${HASS_PVC:-home-assistant-config}"
pod="${HASS_UPLOAD_POD:-ha-upload}"
retries="${HASS_UPLOAD_RETRIES:-5}"
chunk_size="${HASS_UPLOAD_CHUNK_SIZE:-524288}"
bundle=""

usage() {
    cat <<'EOF'
Usage: upload-state-bundle.sh [options] <bundle.tar.gz>

Options:
  --retries N        Attempts per file before failing (default: 5)
  -h, --help         Show this help

Environment:
  HASS_UPLOAD_CHUNK_SIZE  Bytes per chunk (default: 524288)
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --retries) retries="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        -*) echo "unknown option: $1" >&2; usage; exit 1 ;;
        *)
            if [ -n "$bundle" ]; then
                echo "only one bundle may be uploaded" >&2
                usage
                exit 1
            fi
            bundle="$1"
            shift
            ;;
    esac
done

if [ -z "$bundle" ]; then
    usage >&2
    exit 1
fi
if ! [[ "$retries" =~ ^[1-9][0-9]*$ ]]; then
    echo "--retries must be a positive integer" >&2
    exit 1
fi
if ! [[ "$chunk_size" =~ ^[1-9][0-9]*$ ]]; then
    echo "HASS_UPLOAD_CHUNK_SIZE must be a positive integer" >&2
    exit 1
fi
if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl is required" >&2
    exit 1
fi

checksum="$bundle.sha256"

if [ ! -f "$bundle" ] || [ ! -f "$checksum" ]; then
    echo "bundle or checksum missing: $bundle" >&2
    exit 1
fi

cleanup() {
    kubectl -n "$namespace" delete pod "$pod" --ignore-not-found >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
kubectl -n "$namespace" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $pod
spec:
  restartPolicy: Never
  containers:
    - name: upload
      image: alpine:3.20
      command: ["sh", "-c", "sleep 3600"]
      volumeMounts:
        - name: config
          mountPath: /config
  volumes:
    - name: config
      persistentVolumeClaim:
        claimName: $pvc
EOF

kubectl -n "$namespace" wait --for=condition=Ready "pod/$pod" --timeout=180s

exec_in_pod() {
    kubectl -n "$namespace" exec -c upload "$pod" -- "$@"
}

exec_in_pod mkdir -p /config/import

bundle_name="$(basename "$bundle")"
checksum_name="$(basename "$checksum")"

if ! upload_file_chunked "$namespace" "$pod" upload \
    "$bundle" "/config/import/$bundle_name" "$retries" "$chunk_size"; then
    echo "Failed to upload $bundle_name after $retries attempts" >&2
    exit 1
fi

if ! upload_file_chunked "$namespace" "$pod" upload \
    "$checksum" "/config/import/$checksum_name" "$retries" "$chunk_size"; then
    echo "Failed to upload $checksum_name after $retries attempts" >&2
    exit 1
fi

echo "Uploaded $bundle_name to $namespace/$pvc:/config/import/"
