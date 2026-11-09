# Implementation Plan: Workload Image Updates

**Branch**: `main` | **Date**: 2026-11-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-update-workload-images/spec.md`

## Summary

Update two independently published workload images through the existing GitOps path without changing
application code. bus-catcher moves from `0.3.0` to `0.4.0` in both the REST and MCP Deployments; the
new release adds memory-bounded streaming GTFS ingest, automatic schedule loading, and a
cross-process ingest lock. Home Assistant moves to
`main-20261109193052-7e131ee`, which adds tracked configuration and the
`home_sweet_home_agent` custom integration. No separate Home Assistant state seeding is expected:
the existing `seed-config` init container copies `/config-seed` into `/config` on every pod start,
and the rollout restarts the pod. Verification must prove that claim and confirm that `.storage`,
the recorder database, secrets, and Zigbee state are preserved. Documentation pins, the bus OOM
caveat, the seeding decision, and rollback steps are updated together with the manifests.

## Technical Context

**Language/Version**: Kubernetes YAML and Kustomize; no application code changes. Consumed images are
a Node.js backend (bus-catcher `0.4.0`) and a Home Assistant configuration image
(`main-20261109193052-7e131ee`).

**Primary Dependencies**: Flux (Kustomize, image-reflector, image-automation), k3s on DietPi,
`local-path` storage, GHCR, the existing dashboard nginx proxy, and the manually created dashboard
configuration Secret and agent Secrets.

**Storage**: Two existing `local-path` PVCs are involved: `bus-catcher-data` (SQLite bus database)
and `home-assistant-config` (Home Assistant runtime state). Neither PVC definition changes.

**Testing**: `scripts/validate.sh` (kubectl kustomize, kubeconform, yamllint, Python tests, shell
tests, gitleaks) plus live verification on the single-node cluster: Deployments Ready, bus REST/MCP
health and data checks, a forced schedule refresh with no OOMKill, data persistence across a pod
restart, Home Assistant readiness, seed evidence, and preserved runtime state.

**Target Platform**: Single-node k3s on DietPi, `linux/amd64`; both images publish `linux/amd64`.

**Project Type**: GitOps infrastructure manifests and operational documentation.

**Performance Goals**: Both bus Deployments Ready within 10 minutes of reconciliation; Home Assistant
Ready within its existing 10-minute startup budget; forced bus refresh completes without OOMKill and
without blocking health checks.

**Constraints**: Immutable image tags only; no `.storage`, databases, secrets, or backups in Git;
no Tailscale identifiers committed; Flux remains the source of truth; Home Assistant config entry and
Assist pipeline selection remain manual `.storage` state.

**Scale/Scope**: Two image pins in `apps/dashboard`, four image references in `apps/home-assistant`,
two documentation files, and the feature artifacts. No new Kubernetes resources.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- **GitOps as source of truth**: Both image changes are committed and reconciled by Flux. Live
  verification only deletes pods to force a restart; it does not become the desired state. Pass.
- **Reproducible host bootstrap**: No host bootstrap change. The documented verification and rollback
  steps extend the existing runbooks. Pass.
- **Public repositories, private state**: No secret, state, database, or backup is added to Git. The
  Home Assistant seed only copies image content to the existing PVC. Pass.
- **Local-first, documented cloud dependencies**: The update continues to rely on GHCR for image
  pulls; both images are public and were verified pullable. Household runtime stays local. Pass.
- **Recoverability before optimization**: Both changes are reversible by Git pin rollback. The bus
  database and Home Assistant state remain on their PVCs. The seeding path is verified, not assumed.
  Pass.
- **Small, reviewable, validated changes**: The change is a pin bump plus documentation. No code or
  resource shape changes. `scripts/validate.sh` gates the merge. Pass.
- **Clear repository boundaries**: bus-catcher and Home Assistant configuration stay in their owning
  repositories; this repository changes only image references and cluster-facing documentation. The
  Home Assistant custom integration is consumed, not implemented here. Pass.

Post-design re-check: the design adds no Kubernetes resources, Secrets, or cross-repository copies.
All gates remain satisfied. No complexity justification is required.

## Project Structure

### Documentation (this feature)

```text
specs/007-update-workload-images/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── runtime-verification.md
└── checklists/
    └── requirements.md
```

### Source Code (repository root)

```text
apps/
├── dashboard/
│   ├── bus-catcher-rest.yaml        # 0.3.0 -> 0.4.0
│   └── bus-catcher-mcp.yaml         # 0.3.0 -> 0.4.0
└── home-assistant/
    └── deployment.yaml              # four image references + markers

docs/
├── 06-home-assistant.md             # pin, seed decision, verification, rollback
└── 13-dashboard.md                  # bus pin, OOM outcome, refresh behavior
```

**Structure Decision**: Use the existing self-contained app Kustomizations under `apps/`. No new
directories under `apps/` or `infrastructure/`. The only new files are this feature's planning
artifacts.

## Phase 0: Research Summary

See [research.md](./research.md). Key decisions:

- Both bus workloads move together to `ghcr.io/sousa99/bus-catcher-backend:0.4.0`; the image was
  verified public in GHCR. No manifest environment changes are needed because schedule auto-refresh
  defaults to enabled with a 15-minute check interval, and only the REST process ingests.
- The existing 10 GiB memory limit is retained for the first 0.4.0 rollout so the memory-bounded
  ingest can be proven before optimizing the limit.
- Home Assistant moves all four references to the new tag. No separate seed or state-bundle upload is
  required because the seed init container runs on every pod start; verification must still confirm
  the new custom component and preservation of `.storage`, database, secrets, and Zigbee state.
- The custom integration config entry and Assist pipeline selection remain manual UI steps stored in
  `.storage`; they are documented as operator steps, not automated by this repository.
- Rollback is a Git revert of the image pins followed by Flux reconciliation.

## Phase 1: Design Outputs

- [data-model.md](./data-model.md): image pins, bus schedule state, Home Assistant tracked config and
  runtime state, and rollout evidence.
- [contracts/runtime-verification.md](./contracts/runtime-verification.md): observable checks and
  expected results for the affected workloads.
- [quickstart.md](./quickstart.md): runnable update, verification, documentation, and rollback guide.

## Complexity Tracking

No constitution violations.
