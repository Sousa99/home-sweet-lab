#!/usr/bin/env bash
set -euo pipefail

namespace="monitoring"
secret="mosquitto-auth"
rotate="false"

if [[ "${1:-}" == "--rotate" ]]; then
    rotate="true"
elif [[ -n "${1:-}" ]]; then
    echo "usage: $0 [--rotate]" >&2
    exit 2
fi

if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl is required" >&2
    exit 1
fi
if ! command -v docker >/dev/null 2>&1; then
    echo "docker is required" >&2
    exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
    echo "openssl is required" >&2
    exit 1
fi

if ! kubectl get namespace "$namespace" >/dev/null 2>&1; then
    echo "namespace/$namespace does not exist; reconcile the host-metrics app first" >&2
    exit 1
fi

if kubectl -n "$namespace" get secret "$secret" >/dev/null 2>&1 && [[ "$rotate" != "true" ]]; then
    echo "secret/$namespace/$secret already exists; use --rotate to replace it" >&2
    exit 1
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

exporter_password="$(openssl rand -hex 16)"
homeassistant_password="$(openssl rand -hex 16)"

docker run --rm \
    -v "$tmpdir:/work" \
    eclipse-mosquitto:2@sha256:860aeb5d63ce509508f6dcfb2bc8a1c1dd2bc60555b562b45ce90e52d8dabb0f \
    sh -c "mosquitto_passwd -b -c /work/passwd exporter '$exporter_password' && mosquitto_passwd -b /work/passwd homeassistant '$homeassistant_password'"

kubectl -n "$namespace" create secret generic "$secret" \
    --from-file=passwd="$tmpdir/passwd" \
    --from-literal=exporter-username=exporter \
    --from-literal=exporter-password="$exporter_password" \
    --from-literal=homeassistant-username=homeassistant \
    --from-literal=homeassistant-password="$homeassistant_password" \
    --dry-run=client -o yaml | kubectl apply -f -

cat <<EOF
Created secret/$namespace/$secret.

Broker:        mosquitto.$namespace.svc.cluster.local:1883
HA username:   homeassistant
HA password:   $homeassistant_password

Store the HA password in your password manager. It is needed for the Home Assistant MQTT
integration and will not be printed again. The exporter credentials are in the Secret.

If you rotated credentials, restart the broker and exporter and update the Home Assistant MQTT
integration password:
  kubectl -n $namespace rollout restart deployment/mosquitto deployment/host-metrics
EOF
