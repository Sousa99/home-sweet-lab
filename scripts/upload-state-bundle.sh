#!/usr/bin/env bash
set -euo pipefail

namespace="${HASS_NAMESPACE:-home-assistant}"
pvc="${HASS_PVC:-home-assistant-config}"
pod="${HASS_UPLOAD_POD:-ha-upload}"

if [ $# -ne 1 ]; then
    echo "Usage: upload-state-bundle.sh <bundle.tar.gz>" >&2
    exit 1
fi

bundle="$1"
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
kubectl -n "$namespace" exec "$pod" -- mkdir -p /config/import
kubectl -n "$namespace" cp "$bundle" "$pod:/config/import/"
kubectl -n "$namespace" cp "$checksum" "$pod:/config/import/"

echo "Uploaded $(basename "$bundle") to $namespace/$pvc:/config/import/"
