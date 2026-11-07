# Implementation Plan: Agent Workload Deployment

**Branch**: `main` | **Date**: 2026-11-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-agent-deployment/spec.md`

## Summary

Deploy the published `ghcr.io/sousa99/home-sweet-home-agent` image as a Flux-managed workload in a
new `agent` namespace. The app is a self-contained Kustomization under `apps/agent` containing the
namespace, a ConfigMap for non-secret settings and in-cluster Service DNS endpoints, a single-replica
Deployment with hardened security context and HTTP probes, a ClusterIP Service on port 3400, and
Flux image automation that tracks `main-YYYYMMDDHHMMSS-<sha>` tags. Credentials are referenced from
manually created Secrets and never committed. Documentation and the repository map are updated.

## Technical Context

**Language/Version**: Kubernetes YAML, Kustomize; agent image is a Node.js runtime owned by
`home-sweet-home-agent`.

**Primary Dependencies**: Flux (Kustomize, image-reflector, image-automation), k3s, existing
dashboard module MCP Services, Home Assistant.

**Storage**: None; the agent is stateless for this deployment.

**Testing**: `scripts/validate.sh` (kubectl kustomize, kubeconform, yamllint, gitleaks) plus
in-cluster probe verification.

**Target Platform**: Single-node k3s on DietPi, `linux/amd64`.

**Project Type**: GitOps infrastructure manifests.

**Performance Goals**: Pod Ready within 10 minutes of reconcile; probes respond within seconds.

**Constraints**: Cluster-internal only; uid/gid 1000; read-only root; no service account token;
termination grace >= 15s; public GHCR image.

**Scale/Scope**: One Deployment, one Service, one ConfigMap, three manual Secrets, one image
automation set.

## Constitution Check

- GitOps as source of truth: all new resources are committed and reconciled by Flux. Pass.
- Public repositories, private state: no secret material is committed; Secrets are manual. Pass.
- Local-first, documented cloud dependencies: LLM endpoint is the documented cloud dependency. Pass.
- Recoverability: stateless workload recovers by reconciliation; secrets documented. Pass.
- Small, reviewable, validated changes: one self-contained app plus docs; validated by script. Pass.
- Clear repository boundaries: agent runtime stays in `home-sweet-home-agent`. Pass.

## Project Structure

### Documentation (this feature)

```text
specs/006-agent-deployment/
├── spec.md
├── plan.md
├── tasks.md
└── checklists/requirements.md
```

### Source Code (repository root)

```text
apps/
├── kustomization.yaml          # add agent
└── agent/
    ├── kustomization.yaml
    ├── namespace.yaml
    ├── configmap.yaml
    ├── deployment.yaml
    ├── service.yaml
    └── image-automation.yaml
docs/
├── README.md                   # add document 14
├── 07-secrets-and-unsynced-state.md
├── 09-limitations.md
└── 14-agent.md
README.md                       # architecture, status, map, related repos
```

**Structure Decision**: Follow the existing `apps/<workload>` Kustomization pattern used by
`home-assistant`, `host-metrics`, and `dashboard`.

## Complexity Tracking

No constitution violations.
