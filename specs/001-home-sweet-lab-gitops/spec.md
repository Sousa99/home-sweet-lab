# Feature Specification: Home Sweet Lab GitOps Bootstrap

**Feature Branch**: `main`

**Created**: 2026-10-24

**Status**: Draft

**Input**: Bootstrap a lab-wide repository for a single DietPi/k3s host, document the existing
Tailscale, kubeconfig, and Lens setup, install Flux, publish a Home Assistant image that excludes
private state, and move untracked state and backups through a documented bundle workflow.

## User Scenarios & Testing _(mandatory)_

### User Story 1 - Reproduce cluster access from documentation (Priority: P1)

A household operator replaces or rebuilds the lab host and follows the repository documentation to
install DietPi, k3s, and Tailscale, copy the kubeconfig to a development machine, and open the
cluster in Lens.

**Why this priority**: Every other phase depends on reliable access. Today the setup exists only in
the operator's head; without written, verified steps the lab cannot be rebuilt.

**Independent Test**: Follow the documented host and access procedures on a clean machine and
confirm that `kubectl get nodes` and Lens both reach the cluster.

**Acceptance Scenarios**:

1. **Given** a clean DietPi installation, **When** the operator follows the k3s procedure, **Then** the node reports `Ready` and the API server is reachable.
2. **Given** k3s is running and Tailscale is enrolled, **When** the operator copies and merges the kubeconfig, **Then** `kubectl get nodes` works from the development machine without an SSH tunnel.
3. **Given** the kubeconfig is on the development machine, **When** the operator imports it into Lens, **Then** the cluster and its namespaces are visible.
4. **Given** a leaked or stale kubeconfig, **When** the operator follows the rotation procedure, **Then** old credentials stop working and access is restored with new ones.

---

### User Story 2 - Reconcile the cluster from Git with Flux (Priority: P1)

The operator pushes a manifest change and Flux applies it to the cluster without manual `kubectl`
commands. The cluster state is recoverable by replaying the repository.

**Why this priority**: GitOps is the mechanism that makes the lab reviewable, reversible, and
rebuildable. Without it, the repository would be documentation rather than an operating system.

**Independent Test**: Bootstrap Flux, push a harmless change, and observe it reconciled; then
revert it and observe the previous state restored.

**Acceptance Scenarios**:

1. **Given** a bootstrapped Flux installation, **When** the operator runs the status checks, **Then** the Git source and Kustomizations report ready.
2. **Given** a merged manifest change, **When** the reconciliation interval elapses, **Then** the cluster reflects the change without manual intervention.
3. **Given** a bad manifest change, **When** it is reverted in Git, **Then** the cluster returns to the previous state.
4. **Given** the development machine is offline, **When** the cluster is online, **Then** Flux continues reconciling from the last fetched revision.

---

### User Story 3 - Run Home Assistant from a published image (Priority: P2)

Home Assistant runs in the cluster from an image built from the public configuration repository.
Tracked YAML comes from the image; runtime state persists on a volume.

**Why this priority**: This is the first real workload and proves the GitOps and storage model.

**Independent Test**: Deploy Home Assistant, confirm the UI is reachable over the tailnet, make a
tracked configuration change, and confirm it appears after the image and reconciliation cycle.

**Acceptance Scenarios**:

1. **Given** a published configuration image, **When** the Deployment starts, **Then** Home Assistant initializes with the tracked YAML and an empty state volume.
2. **Given** an existing state volume, **When** the pod restarts, **Then** `.storage`, databases, and backups survive while tracked YAML is refreshed from the image.
3. **Given** a new image tag published by the configuration repository, **When** the image automation reconciles, **Then** the Deployment runs the new immutable tag.
4. **Given** the ZBT-2 is attached to the host, **When** Home Assistant starts, **Then** ZHA can use the stable by-id device path.

---

### User Story 4 - Move untracked state and backups deliberately (Priority: P2)

The operator migrates existing Home Assistant state to the cluster with a single bundle, and pulls
backups back to the development machine when desired.

**Why this priority**: The repository is public and cannot carry secrets, databases, or backups.
Without a reliable transfer mechanism, the deployment would lose household state.

**Independent Test**: Create a bundle from an existing Home Assistant configuration, upload it,
restart the workload, and verify entities, secrets, Zigbee configuration, and backups are present.

**Acceptance Scenarios**:

1. **Given** a stopped Home Assistant instance, **When** the operator creates a bundle, **Then** the bundle contains the configured untracked paths and a checksum.
2. **Given** an uploaded bundle, **When** the pod restarts, **Then** the restore step verifies the checksum and extracts it before Home Assistant starts.
3. **Given** an already-applied bundle, **When** the pod restarts again, **Then** the bundle is not applied twice.
4. **Given** a corrupted bundle, **When** the pod starts, **Then** the restore step refuses to extract it and reports a clear error.
5. **Given** backups on the volume, **When** the operator pulls them, **Then** the local copies match the remote checksums.

---

### User Story 5 - Validate and publish changes automatically (Priority: P3)

Manifest changes are validated before merge, and Home Assistant configuration changes produce a
new immutable image.

**Why this priority**: Automation reduces the chance of breaking a single-node household service
and removes manual image builds.

**Independent Test**: Open a pull request with an invalid manifest and confirm validation fails;
merge a configuration change and confirm a new image is published and consumed.

**Acceptance Scenarios**:

1. **Given** an invalid manifest, **When** validation runs, **Then** the change is rejected with a readable error.
2. **Given** a merged Home Assistant configuration change, **When** the publish workflow completes, **Then** a new immutable, publicly pullable image exists.
3. **Given** a published image and image automation, **When** reconciliation runs, **Then** the Deployment references the new tag.
4. **Given** a secret accidentally added to a public repository, **When** the secret scan runs, **Then** the change is rejected.

---

### Edge Cases

- Tailscale is offline when the host boots; the Traefik load balancer has no external address and remote access is unavailable until Tailscale returns.
- The Tailscale IP changes; kubeconfig and ingress assumptions break, and the recovery procedure must be documented.
- The kubeconfig uses a MagicDNS name that is absent from the k3s certificate SANs; TLS verification fails.
- Flux bootstrap runs against a repository that already contains conflicting manifests, or the token lacks repository-write permission.
- The GHCR package is private, the tag does not exist, or the registry is unreachable; the pod stays in image pull failure.
- The persistent volume is lost; the workload must start cleanly and restore from the latest bundle.
- A bundle is truncated, has a mismatched checksum, or is uploaded while Home Assistant is writing state.
- The ZBT-2 is unplugged, its by-id path changes, or the container lacks permission to open the device.
- A tracked YAML file is edited directly on the server and is overwritten at the next restart.
- A manual secret is missing, rotated, or drifted from its documentation.
- A Home Assistant upgrade is incompatible with the baked configuration or the state schema.
- The single node runs out of disk, affecting the volume and backups.
- A secret is accidentally committed to either public repository.

## Requirements _(mandatory)_

### Functional Requirements

- **FR-001**: The repository MUST provide a README, repository guidance, a constitution, and a specification that describe scope, boundaries, and the GitOps model.
- **FR-002**: Documentation MUST describe the host hardware, DietPi prerequisites, and verification steps needed before k3s installation.
- **FR-003**: Documentation MUST describe k3s installation, verification, upgrade, and uninstall, including the default storage class and ingress controller.
- **FR-004**: Documentation MUST describe Tailscale enrollment, MagicDNS, key expiry, access-control expectations, and status verification.
- **FR-005**: Documentation MUST describe kubeconfig retrieval, address rewriting, secure copy to the development machine, context merging, permission restrictions, Lens import, and credential rotation.
- **FR-006**: Documentation MUST describe Flux bootstrap from the development machine, including the required token scope, target path, and post-bootstrap verification.
- **FR-007**: All cluster resources that can be declared MUST live in the repository and be reconciled by Flux; manual application MUST be limited to bootstrap, manual Secrets, state uploads, and documented break-glass recovery.
- **FR-008**: The repository MUST separate the Flux entry point, cluster-wide infrastructure, and per-application manifests into distinct directories.
- **FR-009**: The Home Assistant image MUST be built and published automatically when the configuration repository changes, with immutable tags that can be ordered by publication time.
- **FR-010**: The published image MUST contain only tracked configuration and MUST exclude secrets, runtime state, databases, backups, media, caches, logs, and local environment files.
- **FR-011**: The Home Assistant Deployment MUST use the official upstream image as its base, refresh tracked YAML from the image at start, and persist runtime state on a persistent volume.
- **FR-012**: The persistent volume MUST use the cluster's default storage class, be sized explicitly, and be documented as single-node and non-replicated.
- **FR-013**: Home Assistant MUST be reachable through the cluster ingress over the host's tailnet address, with forwarded-header trust configured and the absence of TLS documented.
- **FR-014**: Documentation and manifests MUST cover the ZBT-2 serial device: host kernel and udev prerequisites, stable by-id path, device mapping into the container, permissions, baud and flow-control settings, ZHA reconfiguration, and fail-fast behavior when the device is absent.
- **FR-015**: The repository MUST provide a script that creates a state bundle from a stopped Home Assistant configuration, including core state, history database, and media/HACS assets, with a checksum file.
- **FR-016**: The repository MUST provide a documented way to upload a bundle to the persistent volume and an in-image restore step that verifies the checksum, extracts the bundle before Home Assistant starts, and records applied bundles idempotently.
- **FR-017**: State bundles MUST exclude tracked YAML and logs, and MUST never be committed to either public repository.
- **FR-018**: Secrets MUST be created manually with documented commands, never committed, and have a documented rotation procedure and drift warning.
- **FR-019**: The repository MUST provide a script that pulls backups from the persistent volume to the development machine and verifies their checksums.
- **FR-020**: Documentation MUST include recovery procedures for pod loss, volume loss, image failure, secret loss, and full cluster rebuild.
- **FR-021**: Flux MUST update the Home Assistant Deployment when a new image tag is published, without manual manifest edits.
- **FR-022**: Continuous validation MUST check manifest rendering, Kubernetes schema conformance, YAML style, and accidental secret exposure before merge.
- **FR-023**: Documentation MUST record the current verified cluster state, including the kubeconfig context, node identity, storage class, and ingress exposure, without exposing tailnet identifiers.
- **FR-024**: Neither public repository MUST contain real tailnet addresses, kubeconfigs, tokens, credentials, state bundles, or household data.
- **FR-025**: Documentation MUST state the v1 limitations: no application TLS, single node, no replicated storage, Tailscale as a cloud dependency, no mDNS discovery, and manual secret management.

### Key Entities

- **Cluster Node**: The single DietPi host running k3s; holds the tailnet address and local storage.
- **Git Source**: The public repository and revision Flux reconciles.
- **Kustomization**: A declared set of resources applied by Flux from a repository path.
- **Image Artifact**: An immutable, publicly pullable Home Assistant image built from tracked configuration.
- **Persistent Volume**: Single-node storage holding Home Assistant runtime state and backups.
- **State Bundle**: A checksummed archive of untracked state, created and uploaded manually.
- **Secret**: A manually created cluster object containing credentials; never stored in Git.
- **Backup Archive**: A Home Assistant backup stored on the volume and pulled to the development machine.

## Success Criteria _(mandatory)_

### Measurable Outcomes

- **SC-001**: A replacement host can be rebuilt to a reachable Kubernetes API in under 60 minutes by following the documentation, excluding Home Assistant state restoration.
- **SC-002**: A merged manifest change is reflected in the running cluster within 10 minutes without manual commands.
- **SC-003**: Reverting a merged change restores the previous behavior within 10 minutes.
- **SC-004**: An uploaded state bundle is fully restored and verified within 10 minutes of restarting the workload.
- **SC-005**: A corrupted or truncated bundle is rejected without altering existing state, and the workload still starts.
- **SC-006**: A backup pull completes within 5 minutes and every local archive matches its remote checksum.
- **SC-007**: A full cluster rebuild plus Home Assistant restore completes within 60 minutes.
- **SC-008**: Secret scanning finds zero credentials, kubeconfigs, state bundles, or household data in either public repository.
- **SC-009**: Home Assistant is reachable from a tailnet-connected phone or laptop without local network access.
- **SC-010**: A new configuration image is running in the cluster within 15 minutes of the configuration merge.

## Assumptions

- The lab is a single node; high availability is out of scope for v1.
- The Home Assistant configuration repository remains public and remains the source of tracked YAML.
- Manual Secret creation is acceptable for v1; a secret manager is future work.
- Home Assistant is served over HTTP inside the tailnet; TLS is deferred.
- The ZBT-2 moves from the development machine to the DietPi host before end-to-end verification.
- The DietPi keeps a stable Tailscale address for the lifetime of the kubeconfig.
- The GHCR package is public so the cluster can pull it without credentials.
- A GitHub token with repository-write access is available at bootstrap time.
- Git history, pull requests, and the constitution are the audit trail for infrastructure changes.
