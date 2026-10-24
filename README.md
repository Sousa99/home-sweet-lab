# Home Sweet Lab

Infrastructure-as-code for the household lab: one k3s node on DietPi, reconciled by Flux from
this repository, reachable over Tailscale, and running Home Assistant on Kubernetes.

This repository owns the **cluster and its workloads**. It does **not** own the Home Assistant
configuration itself; that lives in
[`home-sweet-home-home-assistant`](https://github.com/Sousa99/home-sweet-home-home-assistant).
This repository builds that configuration into an image, deploys it, and documents the parts that
must stay outside Git.

```text
Mac (development) ──git push──▶ GitHub: home-sweet-lab
        │                              │
        │ kubectl / Lens               │ Flux pulls & reconciles
        ▼                              ▼
              DietPi · k3s ◀── Flux controllers
                    │
                    ├── home-assistant namespace
                    │     ├── Deployment (image from the HA repository)
                    │     └── PVC (state, history, backups)
                    └── Traefik ──▶ Tailscale MagicDNS
```

## Status

Phase 1: repository scaffolding, Spec Kit, constitution, and baseline specification.

The host, Flux, and Home Assistant phases are specified in
[`specs/001-home-sweet-lab-gitops/spec.md`](specs/001-home-sweet-lab-gitops/spec.md) and will be
documented under [`docs/`](docs/).

## Architecture

| Layer | Component | Owner |
| ----- | --------- | ----- |
| Host | Old PC running DietPi | This repository (documented) |
| Cluster | k3s, Traefik, `local-path` storage | This repository |
| GitOps | Flux controllers in `flux-system` | This repository |
| Network | Tailscale on the host, MagicDNS | This repository (documented) |
| Deployment | Home Assistant manifests, image tag | This repository |
| Configuration | Home Assistant YAML, automations, dashboards | `home-sweet-home-home-assistant` |
| Private state | `.storage`, DBs, `secrets.yaml`, backups | Manual, never committed |

Git is the source of truth for everything in this repository. Manual `kubectl apply` is reserved
for bootstrap and break-glass recovery.

## Home Assistant image and state

The Home Assistant image is built from the configuration repository and contains only the tracked
YAML. At pod start, an init container copies that YAML into `/config`; a persistent volume keeps
the untracked state (`.storage`, databases, backups, media).

Untracked state is moved deliberately, not by Git:

- **First start / migration:** create a state bundle with `scripts/create-state-bundle.sh`, upload
  it to the persistent volume, and restart Home Assistant.
- **Backups:** Home Assistant writes to `/config/backups`; pull copies to the Mac with
  `scripts/pull-backups.sh`.
- **Never committed:** state bundles, backups, `secrets.yaml`, databases, and Tailscale or
  kubeconfig material.

See [`docs/07-secrets-and-unsynced-state.md`](docs/07-secrets-and-unsynced-state.md) and
[`docs/08-backups-and-recovery.md`](docs/08-backups-and-recovery.md).

## Repository map

```text
clusters/dietpi/          Flux entry point and generated flux-system manifests
infrastructure/           Cluster-wide resources managed by Flux
apps/                     Workloads (Home Assistant first)
scripts/                  Operational helpers (state bundles, backups, validation)
host/                     Host-specific notes and udev rules
docs/                     Setup, access, Flux, Home Assistant, recovery
specs/                    Spec-driven deliverables
```

## Access

- Kubernetes API: kubeconfig copied from the DietPi host; see
  [`docs/04-kubeconfig-and-lens.md`](docs/04-kubeconfig-and-lens.md).
- Lens: imports the same kubeconfig and is used for observation, not as a deployment mechanism.
- Remote access: Tailscale MagicDNS. Real tailnet addresses, hostnames, and credentials are never
  committed.
- Home Assistant: served through Traefik on the host's Tailscale interface, HTTP for now. TLS and
  the Tailscale Operator are deferred and documented as limitations.

## Related repositories

| Repository | Purpose |
| ---------- | ------- |
| `home-sweet-home-home-assistant` | Home Assistant configuration, image build, automations |
| `home-sweet-home-agent` | MCP host, LLM integration, conversation behavior |
| `home-sweet-home-dashboard` | TV / large-screen dashboard |
| `home-sweet-home-modules` | Module implementations and MCP backends |

## Non-goals for v1

High availability, replicated storage, automatic TLS, multi-node scheduling, automated offsite
backups, and migrating the other `home-sweet-home-*` workloads. The layout leaves room for them.

## Safety rules

- Never commit secrets, kubeconfigs, Tailscale addresses, state bundles, or backup archives.
- Validate manifests and Kustomizations before merging.
- Document every manual step and every cloud dependency.
- Test restore paths on the real cluster; a backup that has not been restored is a hypothesis.
