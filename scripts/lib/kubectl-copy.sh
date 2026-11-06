#!/usr/bin/env bash
# Chunked, retrying file transfers over `kubectl exec`.
#
# Source this file from scripts; do not execute it. Callers should already run
# with `set -euo pipefail`, because the upload path relies on pipeline failure
# propagation.

local_sha256() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

remote_sha256() {
    local ns="$1"
    local pod="$2"
    local container="$3"
    local file="$4"
    kubectl -n "$ns" exec -c "$container" "$pod" -- sh -c '
        f=$1
        sha256sum "$f" | cut -d" " -f1
    ' sh "$file"
}

remote_size() {
    local ns="$1"
    local pod="$2"
    local container="$3"
    local file="$4"
    kubectl -n "$ns" exec -c "$container" "$pod" -- sh -c '
        f=$1
        wc -c < "$f" | tr -d " "
    ' sh "$file"
}

fetch_file_chunked() {
    local ns="$1"
    local pod="$2"
    local container="$3"
    local src="$4"
    local dest="$5"
    local retries="${6:-5}"
    local chunk_size="${7:-524288}"
    local tmp="$dest.part.$$"
    local chunk_tmp="$tmp.chunk"
    local attempt=1
    local remote_hash=""
    local size=""
    local actual_hash=""
    local offset=0
    local index=0
    local expected=0
    local actual=""
    local chunk_attempt=1
    local chunk_ok=0
    local ok=1

    while [ "$attempt" -le "$retries" ]; do
        remote_hash="$(remote_sha256 "$ns" "$pod" "$container" "$src" 2>/dev/null || true)"
        size="$(remote_size "$ns" "$pod" "$container" "$src" 2>/dev/null | tr -d ' ' || true)"
        if [ -z "$remote_hash" ] || [ -z "$size" ]; then
            attempt=$((attempt + 1))
            if [ "$attempt" -le "$retries" ]; then
                sleep 1
            fi
            continue
        fi

        rm -f "$tmp" "$chunk_tmp"
        : > "$tmp"
        offset=0
        index=0
        ok=1

        while [ "$offset" -lt "$size" ]; do
            expected="$chunk_size"
            if [ $((size - offset)) -lt "$chunk_size" ]; then
                expected=$((size - offset))
            fi
            chunk_ok=0
            chunk_attempt=1
            while [ "$chunk_attempt" -le "$retries" ]; do
                rm -f "$chunk_tmp"
                if kubectl -n "$ns" exec -c "$container" "$pod" -- sh -c '
                    f=$1
                    i=$2
                    bs=$3
                    dd if="$f" bs="$bs" skip="$i" count=1 2>/dev/null
                ' sh "$src" "$index" "$chunk_size" > "$chunk_tmp" 2>/dev/null; then
                    actual="$(wc -c < "$chunk_tmp" | tr -d ' ')"
                    if [ -n "$actual" ] && [ "$actual" -eq "$expected" ]; then
                        chunk_ok=1
                        break
                    fi
                fi
                chunk_attempt=$((chunk_attempt + 1))
                if [ "$chunk_attempt" -le "$retries" ]; then
                    sleep 1
                fi
            done
            if [ "$chunk_ok" -ne 1 ]; then
                ok=0
                break
            fi
            cat "$chunk_tmp" >> "$tmp"
            rm -f "$chunk_tmp"
            offset=$((offset + expected))
            index=$((index + 1))
        done
        rm -f "$chunk_tmp"

        if [ "$ok" -eq 1 ]; then
            actual_hash="$(local_sha256 "$tmp")"
            if [ "$actual_hash" = "$remote_hash" ]; then
                mv "$tmp" "$dest"
                return 0
            fi
        fi

        rm -f "$tmp"
        attempt=$((attempt + 1))
        if [ "$attempt" -le "$retries" ]; then
            sleep 1
        fi
    done

    rm -f "$tmp" "$chunk_tmp"
    return 1
}

upload_file_chunked() {
    local ns="$1"
    local pod="$2"
    local container="$3"
    local src="$4"
    local dest="$5"
    local retries="${6:-5}"
    local chunk_size="${7:-524288}"
    local tmp="$dest.part.$$"
    local attempt=1
    local src_hash=""
    local size=""
    local remote_hash=""
    local offset=0
    local index=0
    local expected=0
    local chunk_ok=0
    local ok=1

    src_hash="$(local_sha256 "$src")"
    size="$(wc -c < "$src" | tr -d ' ')"
    if [ -z "$src_hash" ] || [ -z "$size" ]; then
        return 1
    fi

    while [ "$attempt" -le "$retries" ]; do
        kubectl -n "$ns" exec -c "$container" "$pod" -- sh -c 'rm -f "$1"' sh "$tmp" >/dev/null 2>&1 || true
        offset=0
        index=0
        ok=1

        while [ "$offset" -lt "$size" ]; do
            expected="$chunk_size"
            if [ $((size - offset)) -lt "$chunk_size" ]; then
                expected=$((size - offset))
            fi
            chunk_ok=0
            if dd if="$src" bs="$chunk_size" skip="$index" count=1 2>/dev/null | \
                kubectl -n "$ns" exec -c "$container" "$pod" -- sh -c 'cat >> "$1"' sh "$tmp"; then
                chunk_ok=1
            fi
            if [ "$chunk_ok" -ne 1 ]; then
                ok=0
                break
            fi
            offset=$((offset + expected))
            index=$((index + 1))
        done

        if [ "$ok" -eq 1 ]; then
            remote_hash="$(remote_sha256 "$ns" "$pod" "$container" "$tmp" 2>/dev/null || true)"
            if [ "$remote_hash" = "$src_hash" ]; then
                if kubectl -n "$ns" exec -c "$container" "$pod" -- sh -c 'mv "$1" "$2"' sh "$tmp" "$dest"; then
                    return 0
                fi
            fi
        fi

        attempt=$((attempt + 1))
        if [ "$attempt" -le "$retries" ]; then
            sleep 1
        fi
    done

    kubectl -n "$ns" exec -c "$container" "$pod" -- sh -c 'rm -f "$1"' sh "$tmp" >/dev/null 2>&1 || true
    return 1
}
