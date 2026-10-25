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

Phase 4: Flux reconciles the Home Assistant deployment from `main`. Home Assistant runs in the
cluster from the published image, private state lives on a 10 GiB PVC, and the UI is reachable at
`http://dietpi/`. Zigbee is connected through `/dev/zbt2`.

The baseline specification is
[`specs/001-home-sweet-lab-gitops/spec.md`](specs/001-home-sweet-lab-gitops/spec.md).

## Documentation

| Document | Covers |
| -------- | ------ |
| [01-hardware-and-dietpi](docs/01-hardware-and-dietpi.md) | Host, DietPi, SSH, timezone, disk |
| [02-k3s](docs/02-k3s.md) | k3s, Traefik, storage, upgrade, uninstall |
| [03-tailscale](docs/03-tailscale.md) | Enrollment, MagicDNS, ACLs, limits |
| [04-kubeconfig-and-lens](docs/04-kubeconfig-and-lens.md) | kubeconfig copy/merge, Lens, rotation |
| [05-flux-bootstrap](docs/05-flux-bootstrap.md) | Flux CLI, token, bootstrap, recovery |
| [06-home-assistant](docs/06-home-assistant.md) | Image, PVC, ingress, ZBT-2, migration |
| [07-secrets-and-unsynced-state](docs/07-secrets-and-unsynced-state.md) | Manual secrets and state bundles |
| [08-backups-and-recovery](docs/08-backups-and-recovery.md) | Backup pull, restore, rebuild |
| [09-limitations](docs/09-limitations.md) | TLS, storage, security, future work |

Host-specific notes: [`host/dietpi/`](host/dietpi/).

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

See the secrets and recovery documents listed in [`docs/`](docs/README.md).

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

- Kubernetes API: kubeconfig copied from the DietPi host; see the access documents in
  [`docs/`](docs/README.md).
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
