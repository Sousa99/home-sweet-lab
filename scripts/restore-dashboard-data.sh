#!/usr/bin/env bash
set -euo pipefail

namespace="${DASHBOARD_NAMESPACE:-dashboard}"
flux_kustomization="${FLUX_APPS_KUSTOMIZATION:-apps}"
pod="dashboard-restore"
image="python:3.12-alpine@sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d"
stateful_deployments=(
    bus-catcher-rest
    bus-catcher-mcp
    procrastinator-tracker-rest
    procrastinator-tracker-mcp
)

if [ $# -ne 1 ]; then
    echo "usage: $0 <dashboard-data.tar.gz>" >&2
    exit 2
fi

archive="$1"

if [ ! -f "$archive" ]; then
    echo "archive not found: $archive" >&2
    exit 1
fi

checksum_file="$(dirname "$archive")/SHA256SUMS"
if [ ! -f "$checksum_file" ]; then
    echo "checksum file not found: $checksum_file; refusing to restore an unverified archive" >&2
    exit 1
fi

if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl is required" >&2
    exit 1
fi

if ! kubectl -n "$namespace" get pvc bus-catcher-data procrastinator-data >/dev/null 2>&1; then
    echo "dashboard PVCs not found in namespace/$namespace" >&2
    exit 1
fi

if command -v sha256sum >/dev/null 2>&1; then
    (cd "$(dirname "$archive")" && sha256sum -c SHA256SUMS)
else
    (cd "$(dirname "$archive")" && shasum -a 256 -c SHA256SUMS)
fi

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
        echo "Restore failed; stateful replicas and Flux were restored." >&2
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
    app.kubernetes.io/name: dashboard-restore
    app.kubernetes.io/part-of: home-sweet-lab
spec:
  restartPolicy: Never
  automountServiceAccountToken: false
  nodeSelector:
    kubernetes.io/hostname: dietpi
    kubernetes.io/arch: amd64
  containers:
    - name: restore
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
        - name: procrastinator
          mountPath: /data/procrastinator
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
kubectl -n "$namespace" cp "$archive" "$pod:/work/dashboard-data.tar.gz"
kubectl -n "$namespace" exec "$pod" -- sh -c '
    set -eu
    find /data/bus-catcher -mindepth 1 -maxdepth 1 -exec rm -rf {} +
    find /data/procrastinator -mindepth 1 -maxdepth 1 -exec rm -rf {} +
    tar -xzf /work/dashboard-data.tar.gz -C /data
    test -s /data/bus-catcher/bus-catcher.db
    test -s /data/procrastinator/procrastinator.db
'

kubectl -n "$namespace" delete pod "$pod" --ignore-not-found >/dev/null 2>&1 || true
kubectl -n "$namespace" scale deployment "${stateful_deployments[@]}" --replicas=1 >/dev/null
scaled_down="false"
resume_flux

for deployment in "${stateful_deployments[@]}"; do
    kubectl -n "$namespace" rollout status "deployment/$deployment" --timeout=5m
done

echo "Restored $(basename "$archive") into namespace/$namespace."
echo "Verify bus/task data in the dashboard and exercise the MCP endpoints."
