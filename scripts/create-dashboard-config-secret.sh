#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
namespace="${DASHBOARD_NAMESPACE:-dashboard}"
secret="${DASHBOARD_CONFIG_SECRET:-dashboard-config}"

if [ $# -ne 1 ]; then
    echo "usage: $0 <config.json>" >&2
    exit 2
fi

config="$1"

if [ ! -f "$config" ]; then
    echo "config file not found: $config" >&2
    exit 1
fi

if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl is required" >&2
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 is required to validate the dashboard config" >&2
    exit 1
fi

python3 "$repo_root/apps/dashboard/validate-config.py" "$config"

if ! kubectl get namespace "$namespace" >/dev/null 2>&1; then
    kubectl create namespace "$namespace" --dry-run=client -o yaml | kubectl apply -f -
fi

kubectl -n "$namespace" create secret generic "$secret" \
    --from-file=config.json="$config" \
    --dry-run=client -o yaml | kubectl apply -f -

echo "Created or updated secret/$namespace/$secret from $(basename "$config")."
echo "The file contents were not printed. Restart the frontend pod to apply a change."
