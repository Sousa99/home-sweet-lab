# Bug Verification: pull-backups.sh completes over a reset exec/websocket stream

- **Slug**: pull-backups-stream-reset
- **Tested**: 2026-11-06
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified

## Summary

The original symptom no longer reproduces with the fixed script: a real-cluster pull to a temporary
destination completed with exit 0, copied all four files, and every `SHA256SUMS` entry verified. The
underlying transport is still flaky — the old `kubectl cp` path and a 5 MiB exec stream still fail —
so the success is attributable to the chunked retry/verification change, not a network improvement.
No regressions were found in the validation suite.

## Checks Performed

| Check | Command / Action | Result | Notes |
|-------|------------------|--------|-------|
| Reproduction (post-fix) | `./scripts/pull-backups.sh --dest <temporary-dir>` | pass | Exit 0; 4 files pulled; `shasum -a 256 -c SHA256SUMS` reported OK for every file; ~1m28s. |
| Original failure mode (control) | `kubectl -n home-assistant cp <ha-pod>:/config/backups/. <temporary-dir>` | fail (expected) | Still exits 1 with `unexpected EOF`; leaves truncated files. Confirms the transport issue persists. |
| Transport-only control | `kubectl -n home-assistant exec <ha-pod> -- dd if=/dev/zero bs=1M count=5 \| wc -c` | fail (expected) | Returned 3,674,107 of 5,242,880 bytes before the stream reset. |
| Negative test (no partial files) | `HASS_BACKUPS_DIR=/config/does-not-exist ./scripts/pull-backups.sh --dest <temporary-dir> --retries 2` | pass | Exit 1 with a clear list failure; destination left empty (no files, no work directory). |
| New / updated tests | `./scripts/tests/test-pull-backups.sh` | pass | `clean`, `retry`, and `permanent-failure` cases all behaved as expected. |
| Regression suite | `./scripts/validate.sh` | pass | kubeconform: 45 resources, 0 invalid; yamllint clean; 31 host-metrics tests (5 skipped); 13 dashboard tests; pull-backups tests; gitleaks: no leaks. |
| Syntax / diff checks | `bash -n scripts/pull-backups.sh`, `bash -n scripts/tests/test-pull-backups.sh`, `git diff --check` | pass | No syntax or whitespace errors. |
| Static analysis | `shellcheck scripts/pull-backups.sh scripts/tests/test-pull-backups.sh scripts/validate.sh` | pass (info only) | `SC2016` is intentional (pod-side `$1`/`$2` expansion); `SC2094` is a false positive (`find` excludes `SHA256SUMS`). |

## Output Excerpts

Post-fix real-cluster pull:

```text
Pulling Automatic_backup_2026.10.4_2026-11-05_04.46_23071844.tar
Pulling Automatic_backup_2026.10.4_2026-11-06_04.47_55078962.tar
Pulling Automatic_backup_2026.10.4_2026-11-06_20.28_49363926.tar
Pulling README.md
./Automatic_backup_2026.10.4_2026-11-06_20.28_49363926.tar: OK
./Automatic_backup_2026.10.4_2026-11-06_04.47_55078962.tar: OK
./Automatic_backup_2026.10.4_2026-11-05_04.46_23071844.tar: OK
./README.md: OK
Pulled 4 file(s) to <temporary-dir>
```

Control — the old single-stream path still fails:

```text
tar: removing leading '/' from member names
E1106 ... "Copying stdout failed" err="read message: unexpected EOF"
error: error reading from error stream: read message: unexpected EOF
old_kubectl_cp_exit=1
```

New test harness:

```text
case clean: exit=0 (expected 0)
case retry: exit=0 (expected 0)
case permanent-failure: exit=1 (expected 1)
All pull-backups tests passed
```

## Residual Risks

- The underlying Tailscale path is still DERP-relayed with symmetric NAT. The fixed script survived it
  in this run, but a completely unavailable or persistently failing path can still exhaust the retry
  budget. The operational network fix remains recommended.
- The helper-pod path (when Home Assistant is stopped) was not exercised on the real cluster. The unit
  test uses the running-pod path. The helper-pod changes (read-only mount, token disabled, cleanup
  ordering) are syntactically valid but not end-to-end tested here.
- `pull-dashboard-data.sh` (~274 MiB), `upload-state-bundle.sh`, and `pull-config.sh` still use the old
  single-stream `kubectl cp` approach and remain vulnerable to the same transport resets. The dashboard
  archive is the highest-risk remaining consumer.
- The final checksum block includes any pre-existing files in the destination. The default
  timestamped destination is empty, so this is not a problem in normal use; reusing `--dest` with
  unrelated files would include them in `SHA256SUMS`. This is pre-existing behavior, not a regression.
- The assessment's open questions about the Mac's network, direct-connect feasibility, SSH/rsync
  availability, and the 2026-10-26 dashboard backup path remain unresolved.
- The Flux controller restart counts (2,000+) are a separate issue and were not investigated here.

## Recommendation

Close the bug — verified end-to-end on the real cluster. The original failure was reproduced as a
control with the old `kubectl cp` path, the fixed script completed and verified all backups, the new
regression tests pass, and the full validation suite is green. Follow up separately on the direct
Tailscale connection and on applying the same chunked/retry treatment to the other bulk-copy scripts.
