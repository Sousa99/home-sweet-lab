#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# shellcheck source=../lib/kubectl-copy.sh
source "$repo_root/scripts/lib/kubectl-copy.sh"

tmp="$(mktemp -d "${TMPDIR:-/tmp}/kubectl-copy-test.XXXXXX")"
trap 'rm -rf "$tmp"' EXIT

stub_dir="$tmp/bin"
remote_dir="$tmp/remote"
src_dir="$tmp/source"
mkdir -p "$stub_dir" "$remote_dir" "$src_dir"

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
            echo "fake-pod"
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
            if [ "${FAKE_FAIL_UPLOADS:-0}" -gt 0 ] && printf '%s\n' "$*" | grep -q 'cat >>'; then
                state="${FAKE_STATE:?}"
                count=0
                [ -f "$state" ] && count="$(cat "$state")"
                if [ "$count" -lt "${FAKE_FAIL_UPLOADS}" ]; then
                    echo $((count + 1)) > "$state"
                    head -c 1000 >/dev/null || true
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

dd if=/dev/urandom of="$src_dir/big.tar" bs=1000 count=1600 2>/dev/null

run_upload() {
    local name="$1"
    local fail_uploads="$2"
    local expected_status="$3"
    local verify="$4"
    local state="$tmp/$name.state"
    local dest="$remote_dir/$name.tar"

    rm -f "$state"
    rm -f "$dest"
    rm -f "$dest".part.* 2>/dev/null || true

    set +e
    PATH="$stub_dir:$PATH" \
    FAKE_FAIL_UPLOADS="$fail_uploads" \
    FAKE_STATE="$state" \
        upload_file_chunked "test-ns" "fake-pod" "fake-container" \
        "$src_dir/big.tar" "$dest" 3 524288 >"$tmp/$name.out" 2>"$tmp/$name.err"
    local status=$?
    set -e

    echo "upload case $name: exit=$status (expected $expected_status)"
    if [ "$status" -ne "$expected_status" ]; then
        cat "$tmp/$name.out" "$tmp/$name.err" >&2
        return 1
    fi

    if [ "$verify" = "ok" ]; then
        cmp "$src_dir/big.tar" "$dest"
    else
        if [ -e "$dest" ]; then
            echo "uploaded file unexpectedly exists: $dest" >&2
            return 1
        fi
        if compgen -G "$dest.part.*" >/dev/null; then
            echo "partial upload files left: $dest.part.*" >&2
            return 1
        fi
    fi
}

run_upload clean 0 0 ok
run_upload retry 2 0 ok
run_upload permanent-failure 999 1 none

echo "All kubectl-copy tests passed"
