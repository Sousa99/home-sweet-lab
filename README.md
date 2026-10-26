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
                    │     ├── PVC (state, history, backups)
                    │     └── Tailscale Ingress ──▶ home-assistant.<tailnet>.ts.net
                    ├── monitoring namespace
                    │     ├── host-metrics exporter ──▶ ClusterIP :9100
                    │     └── mosquitto broker ──▶ ClusterIP :1883 ──▶ HA MQTT
                    ├── dashboard namespace
                    │     ├── dashboard frontend ──▶ Tailscale Ingress :443
                    │     ├── four REST APIs ──▶ ClusterIP :3000
                    │     └── four MCP servers ──▶ ClusterIP :3001
                    ├── tailscale namespace (operator + ingress proxy)
                    └── Traefik ──▶ future apps at /
```

## Status

Phase 8: Flux reconciles Home Assistant, the host-metrics exporter, and the MQTT device-grouping path
from `main`. Home Assistant, the exporter, and Mosquitto are Ready on `dietpi`; retained discovery,
state, and availability are verified. The dashboard stack is reconciled into `dashboard`: the
frontend at `https://dashboard.<tailnet>.ts.net/`, four REST APIs, four MCP servers, and both SQLite
PVCs are live and verified. The configuration Secret is in place, the bus schedule is ingested, and
the backup/restore and failure drills passed. The node-reboot drill remains a maintenance-window
task. The remaining Home Assistant work
is the manual MQTT integration and a maintenance-window node reboot. Home Assistant continues to run
from the published image, private state lives on a 10 GiB PVC, and the UI is served with HTTPS at
`https://home-assistant.<tailnet>.ts.net/`. Zigbee is connected through `/dev/zbt2`. Backup pulls,
manifest validation, and restore hardening are in place; the destructive full-rebuild drills remain
a maintenance-window task.

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
| [09-limitations](docs/09-limitations.md) | Access, storage, security, future work |
| [10-ui-to-git](docs/10-ui-to-git.md) | Pull UI YAML changes into the checkout for review |
| [11-host-metrics](docs/11-host-metrics.md) | HTTP exporter, metric contract, legacy Scrape UI, recovery |
| [12-host-metrics-mqtt](docs/12-host-metrics-mqtt.md) | MQTT broker, one-device discovery, HA MQTT UI, migration |
| [13-dashboard](docs/13-dashboard.md) | Dashboard frontend, REST proxy, MCP services, config, backup, recovery |

Host-specific notes: [`host/dietpi/`](host/dietpi/).

## Architecture

| Layer | Component | Owner |
| ----- | --------- | ----- |
| Host | Old PC running DietPi | This repository (documented) |
| Cluster | k3s, Traefik, `local-path` storage | This repository |
| Ingress | Tailscale Kubernetes Operator for Home Assistant; Traefik for future apps | This repository |
| GitOps | Flux controllers in `flux-system` | This repository |
| Network | Tailscale on the host and the Kubernetes Operator, MagicDNS, HTTPS | This repository (documented) |
| Monitoring | Internal host-metrics exporter and Mosquitto MQTT broker (ClusterIP only); no Prometheus/Grafana | This repository |
| Dashboard | Frontend, four REST APIs, four MCP servers, two SQLite PVCs | This repository |
| Deployment | Home Assistant manifests, image tag; host-metrics manifests; dashboard manifests | This repository |
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

To promote UI-created YAML (automations, scripts, scenes, YAML-mode dashboards) back into Git, run
`scripts/pull-config.sh` (dry-run by default), review the diff, then commit. Storage-mode dashboards
are not pulled; they remain on the PVC and in backups. See
[10-ui-to-git](docs/10-ui-to-git.md).

See the secrets and recovery documents listed in [`docs/`](docs/README.md).

## Repository map

```text
clusters/dietpi/          Flux entry point and generated flux-system manifests
infrastructure/           Cluster-wide resources managed by Flux
apps/                     Workloads (Home Assistant, host-metrics, dashboard)
scripts/                  Operational helpers (config pull, state bundles, backups, validation)
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
- Home Assistant: `https://home-assistant.<tailnet>.ts.net/`, served by the Tailscale Kubernetes
  Operator with a Tailscale-issued certificate. The host's Traefik no longer serves Home Assistant;
  `/` is free for a future landing page.
- Dashboard: `https://dashboard.<tailnet>.ts.net/` after the dashboard stack is reconciled. Only the
  frontend is exposed; REST and MCP stay cluster-internal. See [13-dashboard](docs/13-dashboard.md).

## Related repositories

| Repository | Purpose |
| ---------- | ------- |
| `home-sweet-home-home-assistant` | Home Assistant configuration, image build, automations |
| `home-sweet-home-agent` | MCP host, LLM integration, conversation behavior |
| `home-sweet-home-dashboard` | TV / large-screen dashboard |
| `home-sweet-home-modules` | Module implementations and MCP backends |

## Non-goals for v1

High availability, replicated storage, public TLS/cert-manager, multi-node scheduling, automated
offsite backups, dashboard/MCP authentication, and migrating the agent and modules. The layout leaves
room for them.

## Safety rules

- Never commit secrets, kubeconfigs, Tailscale addresses, state bundles, or backup archives.
- Validate manifests and Kustomizations before merging.
- Document every manual step and every cloud dependency.
- Test restore paths on the real cluster; a backup that has not been restored is a hypothesis.
