# Bug Assessment: pull-backups.sh aborts on a reset exec/websocket stream

- **Slug**: pull-backups-stream-reset
- **Created**: 2026-11-06
- **Source**: pasted text (no URL supplied; URL Trust Policy not exercised)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

Verbatim report from the user:

```text
➜  scripts git:(main) ./pull-backups.sh
Defaulted container "home-assistant" out of: home-assistant, seed-config (init), restore-state (init), configure-http (init)
tar: removing leading '/' from member names
E1106 20:43:19.393056   21292 v2.go:151] "Copying stdout failed" err="next reader: websocket: close 1006 (abnormal closure): unexpected EOF"
E1106 20:43:19.393057   21292 v2.go:168] "Copying stderr failed" err="next reader: websocket: close 1006 (abnormal closure): unexpected EOF"
error: error reading from error stream: next reader: websocket: close 1006 (abnormal closure): unexpected EOF
```

## Symptom

`scripts/pull-backups.sh` starts copying `/config/backups` from the running Home Assistant
pod, then aborts partway through with a websocket/stream reset (`close 1006` or `connection
reset by peer`). The expected behavior is a complete copy of every backup into the timestamped
destination followed by a verified `SHA256SUMS` file.

## Reproduction

Reproduced on 2026-11-06 against the live cluster (kubectl `v1.37.1`, k3s `v1.36.5+k3s1`).

1. `cd ~/Desktop/code/home-sweet-lab`
2. `./scripts/pull-backups.sh`
3. Observe `tar: removing leading '/' from member names`, then a websocket `1006` /
   `connection reset by peer` error; the script exits non-zero before checksumming.
4. Direct reproduction without the script:
   `kubectl -n home-assistant cp <ha-pod>:/config/backups/. /tmp/out/` also fails after
   several megabytes, leaving truncated files.
5. Transport-only reproduction (no PVC I/O):
   `kubectl -n home-assistant exec <ha-pod> -- dd if=/dev/zero bs=1M count=5 | wc -c`
   returned fewer than 5 MiB on 5/5 attempts, while 1 MiB returned in full on 3/3 attempts.
   A single 4.2 MiB backup file also failed on 5/5 `kubectl cp` attempts.
6. Disabling the websocket exec path
   (`KUBECTL_REMOTE_COMMAND_WEBSOCKETS=false`) did not fix it: 5 MiB failed 5/5 over SPDY too,
   so this is not a websocket-protocol bug.

Observed environment while reproducing:

- `tailscale status` routes the node over a DERP relay; `tailscale ping` reports
  `direct connection not established`.
- `tailscale netcheck` reports `MappingVariesByDestIP: true` (hard/symmetric NAT) and DERP
  latency of roughly 250 ms–1.2 s.
- The API server has been up for about 5.4 days (`process_start_time_seconds`), the node has
  no memory/disk pressure, and small control-plane requests (`get`, `logs`, `--raw`) succeed.
- The backups are small (~12 MiB total; largest ~4.2 MiB), and gzip does not shrink them
  (4,444,160 → 4,436,054 bytes), so compression is not a workaround.

## Suspected Code Paths

- `scripts/pull-backups.sh:69` — the single `kubectl cp "$pod:/config/backups/." "$dest/"`
  streams the whole directory over one exec/websocket connection. This is the operation that
  resets.
- `scripts/pull-backups.sh:38-40` — pod selection lacks a `status.phase=Running` filter (unlike
  `pull-config.sh`), so a terminating or failing pod could be selected.
- `scripts/pull-backups.sh:71-89` — checksums are computed only after a successful copy; a
  failed copy leaves truncated files in `$dest` with no `SHA256SUMS` and no cleanup, so partial
  backups can be mistaken for good ones.
- `scripts/pull-config.sh:134` — per-file `kubectl cp`; smaller files are less likely to hit the
  threshold but share the same transport risk.
- `scripts/pull-dashboard-data.sh:163-164` — copies a ~274 MiB archive with `kubectl cp`; this is
  the highest-risk consumer of the same transport.
- `scripts/upload-state-bundle.sh:49-50` — uploads a bundle with `kubectl cp`; same failure mode
  in the restore direction.
- `docs/08-backups-and-recovery.md:30-48` — documents the pull as a normal, expected-to-succeed
  workflow.

## Root Cause Hypothesis

**High confidence** in the mechanism: the `kubectl cp` / `kubectl exec` stream between this Mac
and the k3s API server is being reset at the transport layer after a few megabytes, so the
directory copy (~12 MiB in one stream) cannot complete. The failure is independent of the file
contents (`/dev/zero` fails too), independent of the exec protocol (websocket and SPDY both
fail), and small 1 MiB streams and ordinary API requests succeed, which rules out the script's
tar invocation and the API server itself. The observed path is DERP-relayed Tailscale with
symmetric NAT and high/variable latency; **medium confidence** that the DERP/NAT path (or the
Mac's current uplink) is the exact reason the long-lived TCP stream is dropped, since the
2026-10-25/26 drills recorded successful pulls and a 274 MiB dashboard backup over the same
kubeconfig. The script is not the cause, but it is brittle: one long stream with no retry,
resume, or partial-file cleanup turns a recoverable transport hiccup into a failed backup pull.

## Proposed Remediation

**Preferred** — two parts:

1. **Operational (root cause)**: restore a stable path before relying on bulk copies. Confirm
   with `tailscale ping <dietpi-tailscale-ip>` that a direct connection is established, not
   DERP. If the Mac is on a hotspot or unstable uplink, switch to the home LAN/Ethernet; if
   symmetric NAT prevents direct connections, enable UPnP/NAT-PMP or use a LAN subnet router.
   This is outside Git but should be documented as a prerequisite for backup pulls.
2. **Script hardening (defense in depth)**: change `pull-backups.sh` to avoid one large stream
   and to fail closed:
   - Use a short-lived Alpine helper pod (as the script already does when HA is stopped) and
     `split` each backup into ~512 KiB chunks inside the pod, `kubectl cp` each chunk with a
     bounded retry loop, concatenate the chunks locally, and verify the result against an
     in-pod `sha256sum` of the original file. Chunking keeps each transfer below the observed
     stable size (~1 MiB) and makes retries cheap.
   - Alternatively, if SSH/rsync to the node is available, use
     `rsync --partial --append-verify` for a resumable copy; this is simpler but depends on
     access that is not currently exercised by the script.
   - Copy only completed backup files, not the whole directory in one tar stream, and skip
     files already present with a matching checksum.
   - On failure, delete the partial destination files (or write to a temporary directory and
     rename on success) so a failed run cannot be mistaken for a good backup.
   - Add `--retries N` (default 3–5) and a clear error that names the transport failure and
     points at the Tailscale/direct-connection check.
   - Select the HA pod with `--field-selector=status.phase=Running` and pass `-c home-assistant`
     explicitly to avoid the benign "Defaulted container" warning and wrong-pod selection.

   Do **not** rely on compressing the backups: the HA backup tars are already incompressible.

**Alternatives**:
- Keep a single `kubectl cp` and wrap it in a retry loop: insufficient in the observed state
  (4.2 MiB files failed 5/5 attempts, so retries alone will not converge).
- `kubectl exec ... tar | tar` with retries: same single-stream limitation and no resume.
- Serve the backup over a temporary HTTP server in the helper pod and `curl --continue-at -`
  through `kubectl port-forward`: resumable, but more moving parts and the port-forward stream
  itself can drop.

**Files likely to change**:
- `scripts/pull-backups.sh` (primary)
- `scripts/pull-dashboard-data.sh` (chunk/resume the large archive; highest-risk consumer)
- `scripts/upload-state-bundle.sh` (same transport in the restore direction)
- `scripts/pull-config.sh` (add retry/cleanup for per-file copies)
- `docs/08-backups-and-recovery.md` (document the direct-connection prerequisite, retries, and
  partial-file behavior)
- `docs/04-kubeconfig-and-lens.md` or `docs/03-tailscale.md` (document the `tailscale ping` /
  `netcheck` diagnostic and direct-connection requirement)

**Tests to add or update**:
- A shell test harness that stubs `kubectl` to inject a mid-stream failure and asserts that the
  script retries, reassembles chunks, verifies the checksum, and leaves no partial files.
- A real-cluster drill: pull a >4 MiB backup and a multi-file directory over the current
  Tailscale path; verify `sha256sum -c SHA256SUMS` and compare against the in-pod checksum.
- A negative test: simulate an unrecoverable transport failure and confirm the script exits
  non-zero, cleans up partials, and does not print a success message.
- A regression test for the dashboard archive path, since it is much larger than the HA backups.

## Risks & Considerations

- Chunking adds many API calls and helper-pod complexity; ensure the trap always deletes the
  helper pod and temporary chunk files, and that the helper pod does not expose data on the
  network.
- The dashboard archive is ~274 MiB; 512 KiB chunks mean hundreds of round trips. Consider a
  larger chunk size or a resumable transport for that script specifically.
- `split`/`sha256sum` must exist in the helper image; Alpine's BusyBox provides both. Do not
  run the chunking inside the live Home Assistant container.
- Fixing only `pull-backups.sh` leaves `upload-state-bundle.sh` and `pull-dashboard-data.sh`
  brittle; the transport affects all bulk copies.
- The network fix lives outside Git and may regress; keep the script-level retry/resume as the
  durable mitigation.
- Partial files currently left in `~/backups/home-sweet-lab/<timestamp>/` are a data-integrity
  risk; any cleanup must not delete previously successful pulls.
- Separately, Flux controllers show very high restart counts (2,000+) with exit code 1, while
  the API server itself has been up ~5.4 days. This looks unrelated to the `kubectl cp` reset
  and should be triaged as its own issue; it is not evidence for this bug's root cause.

## Open Questions

- [NEEDS CLARIFICATION: what network is the Mac on when the failure occurs? `netcheck` showed a
  changing gateway and symmetric NAT; is this a hotspot, USB tether, or unstable Wi-Fi?]
- [NEEDS CLARIFICATION: can a direct Tailscale connection be established (home LAN, UPnP/NAT-PMP,
  subnet router), or is DERP the only viable path?]
- [NEEDS CLARIFICATION: did the successful 2026-10-25 pull and 2026-10-26 274 MiB dashboard
  backup run over a direct connection? That would confirm this is a network regression.]
- [NEEDS CLARIFICATION: is SSH/rsync to the node available as an alternative transport? The docs
  assume `ssh dietpi@dietpi`, but SSH from this environment was refused (publickey/password).]
- [NEEDS CLARIFICATION: should the fix cover only `pull-backups.sh` or all bulk `kubectl cp`
  scripts (dashboard, upload, config)?]
- [NEEDS CLARIFICATION: are the Flux controller restarts related to the same node instability,
  or a separate issue?]
