#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
script="$repo_root/scripts/pull-backups.sh"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/pull-backups-test.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

if command -v sha256sum >/dev/null 2>&1; then
    sum_cmd=(sha256sum)
else
    sum_cmd=(shasum -a 256)
fi

stub_dir="$tmp/bin"
src="$tmp/source"
mkdir -p "$stub_dir" "$src"

if ! command -v sha256sum >/dev/null 2>&1; then
    cat > "$stub_dir/sha256sum" <<'EOF'
#!/usr/bin/env bash
exec shasum -a 256 "$@"
EOF
    chmod +x "$stub_dir/sha256sum"
fi

cat > "$stub_dir/kubectl" <<'STUB'
#!/usr/bin/env bash
set -euo pipefail

while [ $# -gt 0 ]; do
    case "$1" in
        -n)
            shift 2
            ;;
        get)
            echo "fake-ha-pod"
            exit 0
            ;;
        delete|wait|apply)
            exit 0
            ;;
        exec)
            shift
            while [ $# -gt 0 ] && [ "$1" != "--" ]; do
                shift
            done
            [ "$1" = "--" ] && shift
            if [ "${FAKE_FAIL_CHUNKS:-0}" -gt 0 ] && printf '%s\n' "$*" | grep -q 'dd if='; then
                state="${FAKE_STATE:?}"
                count=0
                [ -f "$state" ] && count="$(cat "$state")"
                if [ "$count" -lt "${FAKE_FAIL_CHUNKS}" ]; then
                    echo $((count + 1)) > "$state"
                    "$@" | head -c 1000 || true
                    exit 1
                fi
            fi
            exec "$@"
            ;;
        *)
            shift
            ;;
    esac
done
exit 0
STUB
chmod +x "$stub_dir/kubectl"

dd if=/dev/urandom of="$src/big.tar" bs=1000 count=1600 2>/dev/null
printf 'small backup\n' > "$src/small.tar"
printf 'readme\n' > "$src/README.md"

run_case() {
    local name="$1"
    local fail_chunks="$2"
    local expected_status="$3"
    local verify="$4"
    local case_dest="$tmp/$name"
    local state="$tmp/$name.state"
    local out="$tmp/$name.out"
    local err="$tmp/$name.err"

    rm -rf "$case_dest"
    mkdir -p "$case_dest"
    rm -f "$state"

    set +e
    PATH="$stub_dir:$PATH" \
    HASS_BACKUPS_DIR="$src" \
    HASS_PULL_CHUNK_SIZE=524288 \
    FAKE_FAIL_CHUNKS="$fail_chunks" \
    FAKE_STATE="$state" \
        "$script" --dest "$case_dest" --retries 3 >"$out" 2>"$err"
    local status=$?
    set -e

    echo "case $name: exit=$status (expected $expected_status)"
    if [ "$status" -ne "$expected_status" ]; then
        cat "$out" "$err" >&2
        return 1
    fi

    if [ "$verify" = "ok" ]; then
        cmp "$src/big.tar" "$case_dest/big.tar"
        cmp "$src/small.tar" "$case_dest/small.tar"
        cmp "$src/README.md" "$case_dest/README.md"
        ( cd "$case_dest" && "${sum_cmd[@]}" -c SHA256SUMS >/dev/null )
    else
        if [ -n "$(find "$case_dest" -maxdepth 1 -type f -print)" ]; then
            echo "partial files left in $case_dest:" >&2
            find "$case_dest" -maxdepth 1 -type f -print >&2
            return 1
        fi
    fi
}

run_case clean 0 0 ok
run_case retry 2 0 ok
run_case permanent-failure 999 1 none

echo "All pull-backups tests passed"
