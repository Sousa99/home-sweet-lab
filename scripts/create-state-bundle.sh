#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

config_dir="${HOME_ASSISTANT_CONFIG_DIR:-$repo_root/../home-sweet-home/home-sweet-home-home-assistant/config}"
output_dir="$repo_root/bundles"
include_database=1
include_media=1
backups_dir_override=""

usage() {
    cat <<'EOF'
Usage: create-state-bundle.sh [options]

Options:
  --config-dir DIR     Home Assistant config directory
                       (default: ../home-sweet-home/home-sweet-home-home-assistant/config)
  --backups-dir DIR    Directory containing Home Assistant backup archives
                       (default: config/backups, then ../backups if non-empty)
  --output DIR         Output directory (default: <repo>/bundles)
  --no-database        Exclude the recorder history database
  --no-media           Exclude media, TTS, and HACS assets
  -h, --help           Show this help
EOF
}

while [ $# -gt 0 ]; do
    case "$1" in
        --config-dir) config_dir="$2"; shift 2 ;;
        --backups-dir) backups_dir_override="$2"; shift 2 ;;
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

if [ -n "$backups_dir_override" ]; then
    if [ ! -d "$backups_dir_override" ]; then
        echo "backups directory not found: $backups_dir_override" >&2
        exit 1
    fi
    backups_dir="$(cd "$backups_dir_override" && pwd)"
elif [ -d "$config_dir/backups" ] && [ -n "$(ls -A "$config_dir/backups" 2>/dev/null)" ]; then
    backups_dir="$(cd "$config_dir/backups" && pwd)"
elif [ -d "$config_dir/../backups" ] && [ -n "$(ls -A "$config_dir/../backups" 2>/dev/null)" ]; then
    backups_dir="$(cd "$config_dir/../backups" && pwd)"
else
    backups_dir=""
fi

paths=()
for path in .storage secrets.yaml zigbee.db blueprints; do
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

if [ ${#paths[@]} -eq 0 ] && [ -z "$backups_dir" ]; then
    echo "nothing to archive in $config_dir" >&2
    exit 1
fi

mkdir -p "$output_dir"
stamp="$(date +%Y%m%d-%H%M%S)"
bundle="$output_dir/home-assistant-state-$stamp.tar.gz"

echo "Creating $bundle"
echo "  config:  $config_dir"
echo "  backups: ${backups_dir:-none}"
printf '  paths:   %s\n' "${paths[*]:-}"

tar_cmd=(tar -czf "$bundle" -C "$config_dir")
if [ ${#paths[@]} -gt 0 ]; then
    tar_cmd+=("${paths[@]}")
fi
if [ -n "$backups_dir" ]; then
    tar_cmd+=(-C "$(dirname "$backups_dir")" "$(basename "$backups_dir")")
fi
"${tar_cmd[@]}"

if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$bundle" | awk '{print $1}' > "$bundle.sha256"
else
    shasum -a 256 "$bundle" | awk '{print $1}' > "$bundle.sha256"
fi

echo "Checksum: $(cat "$bundle.sha256")"
ls -lh "$bundle" "$bundle.sha256"
