#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
rendered_apps="$tmpdir/apps.yaml"
rendered_infra="$tmpdir/infrastructure.yaml"

if ! command -v kubectl >/dev/null 2>&1; then
    echo "kubectl is required" >&2
    exit 1
fi

echo "Rendering apps/ and infrastructure/"
kubectl kustomize "$repo_root/apps" > "$rendered_apps"
kubectl kustomize "$repo_root/infrastructure" > "$rendered_infra"

if command -v kubeconform >/dev/null 2>&1; then
    echo "Validating Kubernetes schemas"
    kubeconform -strict -summary -ignore-missing-schemas "$rendered_apps" "$rendered_infra"
else
    echo "kubeconform not found; skipping schema validation" >&2
fi

if command -v yamllint >/dev/null 2>&1; then
    echo "Linting YAML"
    yamllint -c "$repo_root/.yamllint" \
        "$repo_root/apps" "$repo_root/infrastructure" \
        "$repo_root/clusters/dietpi/apps.yaml" \
        "$repo_root/clusters/dietpi/infrastructure.yaml"
else
    echo "yamllint not found; skipping YAML lint" >&2
fi

if command -v gitleaks >/dev/null 2>&1; then
    echo "Scanning for secrets"
    gitleaks detect --source "$repo_root" --no-banner --redact
else
    echo "gitleaks not found; skipping secret scan" >&2
fi

echo "Validation passed"
