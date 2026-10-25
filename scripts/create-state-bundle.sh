#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

config_dir="${HOME_ASSISTANT_CONFIG_DIR:-$repo_root/../home-sweet-home/home-sweet-home-home-assistant/config}"
output_dir="$repo_root/bundles"
include_database=1
include_media=1

usage() {
    cat <<'EOF'
Usage: create-state-bundle.sh [options]

Options:
  --config-dir DIR     Home Assistant config directory
                       (default: ../home-sweet-home/home-sweet-home-home-assistant/config)
  --output DIR         Output directory (default: <repo>/bundles)
  --no-database        Exclude the recorder history database
  --no-media           Exclude media, TTS, and HACS assets
  -h, --help           Show this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --config-dir) config_dir="$2"; shift 2 ;;
        --output) output_dir="$2"; shift 2 ;;
        --no-database) include_database=0; shift ;;
        --no-media) include_media=0; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "unknown option: $1" >&2; usage; exit 1 ;;
    esac
done

if [ ! -d "$config_dir" ]; then
    echo "config directory not found: $config_dir" >&2
    exit 1
fi

paths=()
for path in .storage secrets.yaml zigbee.db blueprints backups; do
    [ -e "$config_dir/$path" ] && paths+=("$path")
done

if [ "$include_database" -eq 1 ]; then
    for path in home-assistant_v2.db home-assistant_v2.db-wal home-assistant_v2.db-shm; do
        [ -e "$config_dir/$path" ] && paths+=("$path")
    done
fi

if [ "$include_media" -eq 1 ]; then
    for path in media tts www/community; do
        [ -e "$config_dir/$path" ] && paths+=("$path")
    done
fi

if [ ${#paths[@]} -eq 0 ]; then
    echo "nothing to archive in $config_dir" >&2
    exit 1
fi

mkdir -p "$output_dir"
stamp="$(date +%Y%m%d-%H%M%S)"
bundle="$output_dir/home-assistant-state-$stamp.tar.gz"

echo "Creating $bundle"
echo "  config: $config_dir"
printf '  paths:  %s\n' "${paths[*]}"

tar -czf "$bundle" -C "$config_dir" "${paths[@]}"

if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$bundle" | awk '{print $1}' > "$bundle.sha256"
else
    shasum -a 256 "$bundle" | awk '{print $1}' > "$bundle.sha256"
fi

echo "Checksum: $(cat "$bundle.sha256")"
ls -lh "$bundle" "$bundle.sha256"
