#!/usr/bin/env bash
set -euo pipefail

namespace="${DASHBOARD_NAMESPACE:-dashboard}"
flux_kustomization="${FLUX_APPS_KUSTOMIZATION:-apps}"
pod="dashboard-backup"
image="python:3.12-alpine@sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d"
dest_root="${DASHBOARD_BACKUP_DIR:-$HOME/backups/home-sweet-lab/dashboard}"
stateful_deployments=(
    bus-catcher-rest
    bus-catcher-mcp
    procrastinator-tracker-rest
    procrastinator-tracker-mcp
)

while [ $# -gt 0 ]; do
    case "$1" in
        --dest)
            if [ $# -lt 2 ]; then
                echo "--dest requires a directory" >&2
                exit 2
            fi
            dest_root="$2"
            shift 2
            ;;
        --dest=*)
            dest_root="${1#--dest=}"
            shift
            ;;
        *)
            echo "usage: $0 [--dest DIR]" >&2
            exit 2
            ;;
    esac
done

if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl is required" >&2
    exit 1
fi

if ! kubectl -n "$namespace" get pvc bus-catcher-data procrastinator-data >/dev/null 2>&1; then
    echo "dashboard PVCs not found in namespace/$namespace; reconcile the dashboard app first" >&2
    exit 1
fi

timestamp="$(date +%Y%m%d-%H%M%S)"
dest="$dest_root/$timestamp"
scaled_down="false"
suspended_here="false"
flux_was_suspended="false"

if kubectl -n flux-system get kustomization "$flux_kustomization" >/dev/null 2>&1; then
    flux_was_suspended="$(kubectl -n flux-system get kustomization "$flux_kustomization" -o jsonpath='{.spec.suspend}' 2>/dev/null || true)"
fi

resume_flux() {
    if [ "$suspended_here" = "true" ]; then
        kubectl -n flux-system patch kustomization "$flux_kustomization" \
            --type merge -p '{"spec":{"suspend":false}}' >/dev/null 2>&1 || true
        if command -v flux >/dev/null 2>&1; then
            flux reconcile kustomization "$flux_kustomization" --with-source >/dev/null 2>&1 || true
        fi
        suspended_here="false"
    fi
}

cleanup() {
    status=$?
    set +e
    kubectl -n "$namespace" delete pod "$pod" --ignore-not-found >/dev/null 2>&1
    if [ "$scaled_down" = "true" ]; then
        kubectl -n "$namespace" scale deployment "${stateful_deployments[@]}" --replicas=1 >/dev/null 2>&1
    fi
    resume_flux
    if [ "$status" -ne 0 ]; then
        echo "Backup failed; stateful replicas and Flux were restored." >&2
    fi
    exit "$status"
}
trap cleanup EXIT INT TERM

if [ "$flux_was_suspended" != "true" ]; then
    kubectl -n flux-system patch kustomization "$flux_kustomization" \
        --type merge -p '{"spec":{"suspend":true}}' >/dev/null
    suspended_here="true"
fi

echo "Stopping stateful dashboard writers"
kubectl -n "$namespace" scale deployment "${stateful_deployments[@]}" --replicas=0 >/dev/null
scaled_down="true"

for module in bus-catcher procrastinator-tracker; do
    for _ in $(seq 1 60); do
        if [ -z "$(kubectl -n "$namespace" get pods -l "app.kubernetes.io/name=$module" -o name 2>/dev/null)" ]; then
            break
        fi
        sleep 2
    done
done

if [ -n "$(kubectl -n "$namespace" get pods -l 'app.kubernetes.io/name in (bus-catcher,procrastinator-tracker)' -o name 2>/dev/null || true)" ]; then
    echo "stateful pods did not stop in time" >&2
    exit 1
fi

kubectl -n "$namespace" delete pod "$pod" --ignore-not-found >/dev/null 2>&1 || true
kubectl -n "$namespace" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $pod
  labels:
    app.kubernetes.io/name: dashboard-backup
    app.kubernetes.io/part-of: home-sweet-lab
spec:
  restartPolicy: Never
  automountServiceAccountToken: false
  nodeSelector:
    kubernetes.io/hostname: dietpi
    kubernetes.io/arch: amd64
  containers:
    - name: backup
      image: $image
      imagePullPolicy: IfNotPresent
      command: ["sh", "-c", "sleep 3600"]
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        privileged: false
        capabilities:
          drop:
            - ALL
      volumeMounts:
        - name: bus-catcher
          mountPath: /data/bus-catcher
          readOnly: true
        - name: procrastinator
          mountPath: /data/procrastinator
          readOnly: true
        - name: work
          mountPath: /work
  volumes:
    - name: bus-catcher
      persistentVolumeClaim:
        claimName: bus-catcher-data
    - name: procrastinator
      persistentVolumeClaim:
        claimName: procrastinator-data
    - name: work
      emptyDir: {}
EOF

kubectl -n "$namespace" wait --for=condition=Ready "pod/$pod" --timeout=180s
kubectl -n "$namespace" exec "$pod" -- sh -c '
    set -eu
    cd /data
    tar -czf /work/dashboard-data.tar.gz bus-catcher procrastinator
    cd /work
    sha256sum dashboard-data.tar.gz > SHA256SUMS
'

mkdir -p "$dest"
kubectl -n "$namespace" cp "$pod:/work/dashboard-data.tar.gz" "$dest/dashboard-data.tar.gz"
kubectl -n "$namespace" cp "$pod:/work/SHA256SUMS" "$dest/SHA256SUMS"

if command -v sha256sum >/dev/null 2>&1; then
    (cd "$dest" && sha256sum -c SHA256SUMS)
else
    (cd "$dest" && shasum -a 256 -c SHA256SUMS)
fi

kubectl -n "$namespace" delete pod "$pod" --ignore-not-found >/dev/null 2>&1 || true
kubectl -n "$namespace" scale deployment "${stateful_deployments[@]}" --replicas=1 >/dev/null
scaled_down="false"
resume_flux

for deployment in "${stateful_deployments[@]}"; do
    kubectl -n "$namespace" rollout status "deployment/$deployment" --timeout=5m
done

echo "Backup written to $dest"
echo "Archive:  dashboard-data.tar.gz"
echo "Checksum: SHA256SUMS"
