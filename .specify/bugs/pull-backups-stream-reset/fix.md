# Bug Fix: pull-backups.sh now survives reset exec/websocket streams

- **Slug**: pull-backups-stream-reset
- **Fixed**: 2026-11-06
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

`scripts/pull-backups.sh` no longer copies `/config/backups` in one long
`kubectl cp` stream. It now reads each backup in 512 KiB `dd` ranges with a
bounded per-chunk retry loop, reassembles and verifies each file against the
SHA-256 computed inside the pod, and only moves verified files into the
destination. This lets a pull complete over the observed DERP-relayed
Tailscale path that resets long-lived streams after a few megabytes.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `scripts/pull-backups.sh` | modified | Chunked `dd` reads, per-chunk retries, in-pod SHA-256 verification, atomic move into the destination, no partial files, `--retries`, `HASS_PULL_CHUNK_SIZE`, explicit container, running-pod filter, `kubectl` presence check. |
| `scripts/tests/test-pull-backups.sh` | added | Stubbed-`kubectl` regression test for clean copy, transient chunk failures, and permanent failure. |
| `scripts/validate.sh` | modified | Runs the pull-backups test alongside the existing Python tests. |
| `docs/08-backups-and-recovery.md` | modified | Documents chunking/retries, the no-partial-files guarantee, the Tailscale direct-connection diagnostic, and the 2026-11-06 drill result. |
| `docs/04-kubeconfig-and-lens.md` | modified | Notes that bulk transfers need a direct tailnet path, not DERP. |

## Diff Highlights

The core change is a retryable chunk reader:

```bash
fetch_chunk() {
    # ...
    if exec_in_pod sh -c '
        f=$1; i=$2; bs=$3
        dd if="$f" bs="$bs" skip="$i" count=1 2>/dev/null
    ' sh "$source_dir/$file" "$index" "$chunk_size" > "$out" 2>"$err"; then
        actual="$(wc -c < "$out" | tr -d ' ')"
        if [ -n "$actual" ] && [ "$actual" -eq "$expected" ]; then
            return 0
        fi
    fi
    # ... retry up to $retries
}
```

Each file is assembled in a temporary directory inside the destination, checked
against the pod-side hash, and only then moved into place:

```bash
actual_hash="$(sum_file "$assembled")"
if [ "$actual_hash" != "$hash" ]; then
    echo "Checksum mismatch for $file ..." >&2
    exit 1
fi
```

## Tests Added or Updated

- `scripts/tests/test-pull-backups.sh` — runs three cases with a fake `kubectl`:
  - `clean`: every chunk succeeds; all files match the source and `SHA256SUMS` verifies.
  - `retry`: the first two chunk reads fail mid-stream; the script retries and completes.
  - `permanent-failure`: every chunk read fails; the script exits non-zero and leaves no files.
- `scripts/validate.sh` now invokes the test, so CI covers it.

## Local Verification

- `bash -n scripts/pull-backups.sh` → syntax OK.
- `bash -n scripts/tests/test-pull-backups.sh` → syntax OK.
- `./scripts/tests/test-pull-backups.sh` → all three cases passed.
- `./scripts/validate.sh` → `Validation passed` (kubeconform 45 resources, yamllint, 31 host-metrics tests, 13 dashboard tests, pull-backups tests, gitleaks: no leaks).
- Real cluster drill: `./scripts/pull-backups.sh --dest <temporary-dir> --retries 6` → pulled 4 files (three backups plus `README.md`) over the current DERP-relayed Tailscale path in about 1m32s; `SHA256SUMS` verified every file against the in-pod hash. Before the fix, the same copy failed reproducibly after 2–4 MiB.
- `git diff --check` → clean.
- `shellcheck` → only info-level `SC2016` (intentional pod-side `$1`/`$2` expansion) and `SC2094` (false positive: `find` excludes `SHA256SUMS`); no errors.

## Deviations from Assessment

- The assessment suggested `split` inside the pod plus `kubectl cp` per chunk. The
  implementation uses `dd bs=... skip=... count=1` ranges instead. The retry and
  chunking properties are the same, but this avoids writing chunk files to the
  pod and avoids `kubectl cp`'s tar layer entirely. This is a lower-risk,
  smaller change than staging chunks on the PVC or in the container filesystem.
- The assessment listed `pull-dashboard-data.sh`, `upload-state-bundle.sh`, and
  `pull-config.sh` as likely to change. The preferred remediation targeted
  `pull-backups.sh`; those scripts are left as follow-ups to keep this fix
  reviewable. They share the same transport risk and should get the same
  treatment next.
- Added a test hook, `HASS_BACKUPS_DIR` (default `/config/backups`), so the
  stub-based test can run without a cluster. It does not change production
  behavior.
- Added the test invocation to `scripts/validate.sh` so CI runs it; this file
  was not in the assessment's list.
- Added a drill-result row to `docs/08` and a short note to `docs/04`; both were
  called for by the assessment's documentation guidance.
- The operational root-cause fix (establishing a direct Tailscale connection)
  is outside Git. It is documented as a diagnostic and recommendation rather
  than applied here.

## Follow-ups

- Apply the same chunked/retry pattern to `scripts/pull-dashboard-data.sh`
  (the ~274 MiB archive is the highest-risk bulk copy), `scripts/upload-state-bundle.sh`,
  and `scripts/pull-config.sh`. Consider extracting the chunk reader into a
  shared `scripts/lib/` helper to avoid four copies.
- Investigate why the Mac's tailnet path is DERP-relayed with symmetric NAT
  (`tailscale netcheck`, `tailscale ping`); a direct connection is the real
  performance and reliability fix. Document the chosen network fix in
  `docs/03-tailscale.md`.
- Tune `HASS_PULL_CHUNK_SIZE` for the dashboard archive; 512 KiB is conservative
  for the small Home Assistant backups but means many round trips for hundreds
  of megabytes. A resumable protocol (`rsync --partial --append-verify` over
  SSH, or HTTP range requests through a port-forward) may be better there.
- Consider skipping backups already present in the destination with a matching
  checksum, and copying only completed backup files while Home Assistant is
  writing a new one.
- The Flux controllers still show very high restart counts (2,000+) with exit
  code 1. That looks unrelated to this bug and should be assessed separately.
- The assessment's open questions remain: the Mac's network context, whether a
  direct tailnet connection is achievable, whether SSH/rsync is available, and
  whether the 2026-10-26 dashboard backup ran over a direct path.
