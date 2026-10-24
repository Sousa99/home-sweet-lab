# Home Sweet Lab Constitution

## Core Principles

### I. GitOps as Source of Truth

Every cluster resource that can be declared MUST live in this repository and be reconciled by Flux.
Manual `kubectl apply` is limited to bootstrap, manual Secret creation, state-bundle uploads, and
break-glass recovery. Any break-glass action MUST be followed by a commit that makes the observed
state reproducible.

### II. Reproducible Host Bootstrap

The DietPi installation, k3s setup, Tailscale enrollment, kubeconfig retrieval, and Flux bootstrap
MUST be documented as ordered, copy-pasteable procedures. A replacement host MUST be buildable from
the documentation alone. Manual steps MUST state their prerequisites, verification command, and
failure behavior.

### III. Public Repositories, Private State

This repository and the Home Assistant configuration repository are public. Secrets, kubeconfigs,
tailnet identifiers, state bundles, databases, backup archives, and household data MUST NOT be
committed. Home Assistant runtime state is stored on a persistent volume and moved deliberately;
it is never part of an image or a Git commit.

### IV. Local-First, Documented Cloud Dependencies

Household services MUST run on household hardware. Every cloud dependency (GitHub, GHCR,
Tailscale, certificate authorities) MUST be documented with its purpose, failure mode, and local
degradation behavior. Remote access MUST NOT be required for local automations to keep working.

### V. Recoverability Before Optimization

A single-node cluster with non-replicated storage is acceptable only if recovery is documented and
tested. Backups MUST have a restore procedure, and the procedure MUST be exercised on the real
cluster. Changes that reduce recoverability require explicit justification.

### VI. Small, Reviewable, Validated Changes

Changes MUST be small enough to review and revert. Manifests MUST pass validation before merge.
Image references MUST use immutable tags or digests. A change that cannot be validated locally
MUST include the exact verification steps performed on the cluster.

### VII. Clear Repository Boundaries

This repository owns the lab infrastructure and workload deployments. It does not own Home
Assistant configuration, the MCP agent, the dashboard, or module implementations. Cross-repository
dependencies MUST be documented rather than copied.

## Technology Standards

- Kubernetes distribution: k3s, single control-plane node on DietPi.
- GitOps controller: Flux, bootstrapped into `flux-system`.
- Ingress: Traefik, exposed on the host's Tailscale interface; HTTPS is deferred and documented.
- Storage: the default `local-path` StorageClass; application-level backups are mandatory.
- Images: published to GHCR, publicly pullable, tagged with immutable, sortable identifiers.
- Home Assistant: official upstream image as the base; configuration baked at `/config-seed`;
  writable state on a PersistentVolumeClaim.
- Manifests: YAML and Kustomize. Helm requires justification and MUST be reconciled by Flux.
- Secrets: manual `kubectl` creation for v1, documented per secret; never committed.

## Repository Boundaries

- `home-sweet-home-home-assistant` owns Home Assistant configuration and image publication.
- `home-sweet-home-agent` owns MCP sessions, LLM calls, authorization, and conversation behavior.
- `home-sweet-home-dashboard` owns the TV dashboard.
- `home-sweet-home-modules` owns module implementations and MCP backends.
- This repository owns the cluster, cluster add-ons, workload manifests, access procedures, and
  recovery documentation.

## Development Workflow

1. Describe the intended change and its failure behavior.
2. Update manifests and documentation together.
3. Validate manifests locally.
4. Reconcile through Flux and verify normal, unavailable, and recovery behavior.
5. Record hardware-specific setup and manual steps.

## Governance

This constitution governs this repository. Material amendments require a documented reason, the
affected household behavior, migration steps, and explicit approval before implementation. The
constitution supersedes convenience; complexity MUST be justified against these principles.

**Version**: 1.0.0 | **Ratified**: 2026-10-24 | **Last Amended**: 2026-10-24
