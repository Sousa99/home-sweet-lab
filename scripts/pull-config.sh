#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

ha_repo="${HOME_ASSISTANT_REPO:-$repo_root/../home-sweet-home/home-sweet-home-home-assistant}"
namespace="${HASS_NAMESPACE:-home-assistant}"
pvc="${HASS_PVC:-home-assistant-config}"
apply=0
force=0
helper_created=0
staging="$(mktemp -d)"
pod=""
container=""

usage() {
    cat <<'EOF'
Usage: pull-config.sh [options]

Pulls tracked-safe Home Assistant YAML from the cluster into the local
home-sweet-home-home-assistant checkout for review and commit.

Options:
  --apply            Copy changed files into the local checkout
  --force            Apply even if target files have uncommitted changes
  --repo DIR         Home Assistant checkout
                     (default: ../home-sweet-home/home-sweet-home-home-assistant)
  --namespace NAME   Home Assistant namespace (default: home-assistant)
  -h, --help         Show this help

What is pulled:
  config/*.yaml (except secrets.yaml and *.secret.yaml)
  config/dashboards/**/*.yaml
  config/packages/**/*.yaml

What is never pulled:
  .storage, secrets.yaml, databases, backups, logs, media, TTS, HACS assets,
  blueprints

Default is a dry run. Nothing is committed or pushed.
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --apply) apply=1; shift ;;
        --force) force=1; shift ;;
        --repo) ha_repo="$2"; shift 2 ;;
        --namespace) namespace="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

if [ ! -d "$ha_repo/config" ]; then
    alt="$repo_root/../home-sweet-home-home-assistant"
    if [ -d "$alt/config" ]; then
        ha_repo="$alt"
    else
        echo "Home Assistant checkout not found: $ha_repo" >&2
        exit 1
    fi
fi
config_dir="$ha_repo/config"

cleanup() {
    rm -rf "$staging"
    if [ "$helper_created" -eq 1 ]; then
        kubectl -n "$namespace" delete pod ha-config-pull --ignore-not-found >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

pod="$(kubectl -n "$namespace" get pod \
    -l app.kubernetes.io/name=home-assistant \
    --field-selector=status.phase=Running \
    -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"

if [ -z "$pod" ]; then
    echo "No running Home Assistant pod; creating a helper pod."
    kubectl -n "$namespace" delete pod ha-config-pull --ignore-not-found >/dev/null 2>&1 || true
    kubectl -n "$namespace" apply -f - <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: ha-config-pull
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
    kubectl -n "$namespace" wait --for=condition=Ready pod/ha-config-pull --timeout=180s
    pod="ha-config-pull"
    container="pull"
    helper_created=1
fi

if [ -z "$container" ]; then
    container="home-assistant"
fi

list_cmd='
{
  for f in /config/*.yaml; do
    [ -e "$f" ] || continue
    case "$f" in
      /config/secrets.yaml|*.secret.yaml) continue ;;
    esac
    echo "${f#/config/}"
  done
  find /config/dashboards /config/packages -type f -name "*.yaml" 2>/dev/null | sed "s#^/config/##"
} | sort -u
'

files="$(kubectl -n "$namespace" exec -c "$container" "$pod" -- sh -c "$list_cmd")"
if [ -z "$files" ]; then
    echo "No allowlisted YAML files found in $namespace/$pod:/config" >&2
    exit 1
fi

while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    mkdir -p "$staging/$(dirname "$rel")"
    kubectl -n "$namespace" cp -c "$container" "$pod:/config/$rel" "$staging/$rel" >/dev/null
done <<< "$files"

changed=()
new=()
unchanged=()

while IFS= read -r rel; do
    [ -n "$rel" ] || continue
    local_file="$config_dir/$rel"
    staged_file="$staging/$rel"
    if [ ! -e "$local_file" ]; then
        new+=("$rel")
    elif cmp -s "$local_file" "$staged_file"; then
        unchanged+=("$rel")
    else
        changed+=("$rel")
    fi
done <<< "$files"

echo "Pulled $(printf '%s\n' "$files" | wc -l | tr -d ' ') allowlisted file(s)."
echo "  unchanged: ${#unchanged[@]}"
echo "  changed:   ${#changed[@]}"
echo "  new:       ${#new[@]}"
echo

if [ ${#changed[@]} -gt 0 ]; then
    for rel in "${changed[@]}"; do
        echo "### changed: $rel"
        diff -u "$config_dir/$rel" "$staging/$rel" || true
        echo
    done
fi

if [ ${#new[@]} -gt 0 ]; then
    for rel in "${new[@]}"; do
        echo "### new: $rel"
        diff -u /dev/null "$staging/$rel" || true
        echo
    done
fi

if [ ${#changed[@]} -eq 0 ] && [ ${#new[@]} -eq 0 ]; then
    echo "No changes."
    exit 0
fi

if command -v gitleaks >/dev/null 2>&1; then
    if ! gitleaks dir "$staging" --no-banner --redact >/dev/null 2>&1; then
        echo "Secret scan failed on the staged files; refusing to continue." >&2
        exit 1
    fi
fi

if [ "$apply" -eq 0 ]; then
    echo "Dry run only. Re-run with --apply to update $ha_repo."
    exit 0
fi

targets=()
if [ ${#changed[@]} -gt 0 ]; then
    for rel in "${changed[@]}"; do targets+=("config/$rel"); done
fi
if [ ${#new[@]} -gt 0 ]; then
    for rel in "${new[@]}"; do targets+=("config/$rel"); done
fi

if [ "$force" -eq 0 ] && git -C "$ha_repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    dirty="$(git -C "$ha_repo" status --porcelain -- "${targets[@]}")"
    if [ -n "$dirty" ]; then
        echo "Target files have uncommitted changes:" >&2
        printf '%s\n' "$dirty" >&2
        echo "Commit or stash them first, or use --force." >&2
        exit 1
    fi
fi

if [ ${#changed[@]} -gt 0 ]; then
    for rel in "${changed[@]}"; do
        mkdir -p "$config_dir/$(dirname "$rel")"
        cp "$staging/$rel" "$config_dir/$rel"
    done
fi
if [ ${#new[@]} -gt 0 ]; then
    for rel in "${new[@]}"; do
        mkdir -p "$config_dir/$(dirname "$rel")"
        cp "$staging/$rel" "$config_dir/$rel"
    done
fi

echo "Applied ${#changed[@]} changed and ${#new[@]} new file(s) to $ha_repo."
if git -C "$ha_repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$ha_repo" status --short -- "${targets[@]}" || true
    git -C "$ha_repo" diff --stat -- "${targets[@]}" || true
fi
echo "Review the diff and commit in $ha_repo."
