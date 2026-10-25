#!/usr/bin/env bash
set -euo pipefail

namespace="${HASS_NAMESPACE:-home-assistant}"
pvc="${HASS_PVC:-home-assistant-config}"
dest="${HOME}/backups/home-sweet-lab/$(date +%Y%m%d-%H%M%S)"
helper_created=0

usage() {
    cat <<'EOF'
Usage: pull-backups.sh [options]

Options:
  --dest DIR        Destination directory (default: ~/backups/home-sweet-lab/<timestamp>)
  --namespace NAME  Home Assistant namespace (default: home-assistant)
  -h, --help        Show this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --dest) dest="$2"; shift 2 ;;
        --namespace) namespace="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

cleanup() {
    if [ "$helper_created" -eq 1 ]; then
        kubectl -n "$namespace" delete pod ha-backup-pull --ignore-not-found >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

mkdir -p "$dest"

pod="$(kubectl -n "$namespace" get pod \
    -l app.kubernetes.io/name=home-assistant \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"

if [ -z "$pod" ]; then
    echo "No running Home Assistant pod; creating a helper pod."
    kubectl -n "$namespace" delete pod ha-backup-pull --ignore-not-found >/dev/null 2>&1
    kubectl -n "$namespace" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: ha-backup-pull
spec:
  restartPolicy: Never
  containers:
    - name: pull
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
    kubectl -n "$namespace" wait --for=condition=Ready pod/ha-backup-pull --timeout=180s
    pod="ha-backup-pull"
    helper_created=1
fi

kubectl -n "$namespace" cp "$pod:/config/backups/." "$dest/"

shopt -s nullglob
files=("$dest"/*)
if [ ${#files[@]} -eq 0 ]; then
    echo "No backups found in $namespace/$pvc:/config/backups" >&2
    exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
    sum_cmd=(sha256sum)
else
    sum_cmd=(shasum -a 256)
fi

(
    cd "$dest"
    find . -maxdepth 1 -type f ! -name SHA256SUMS \
        -exec "${sum_cmd[@]}" {} + > SHA256SUMS
    "${sum_cmd[@]}" -c SHA256SUMS
)

echo "Pulled ${#files[@]} file(s) to $dest"
ls -lh "$dest"
