# Implementation Plan: Host Metrics Exporter and Home Assistant Integration

**Branch**: `main` (feature directory `specs/002-host-metrics-exporter`) | **Date**: 2026-10-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/002-host-metrics-exporter/spec.md`

## Summary

Deploy a stateless, single-replica host-metrics exporter in a new `monitoring` namespace, reconciled
by the existing Flux `apps` Kustomization. The exporter is a small Python 3.12 standard-library
program, delivered as a Git-tracked script through a Kustomize-generated ConfigMap and run from the
official `python:3.12-alpine` image pinned by digest. It reads the DietPi host through read-only
hostPath mounts, exposes Prometheus text at `/metrics`, a Home Assistant-friendly JSON projection at
`/ha`, and liveness/readiness endpoints, and is reachable only through a ClusterIP Service at
`host-metrics.monitoring.svc.cluster.local:9100`.

Home Assistant is integrated manually through the built-in Scrape integration in the UI. The
`/ha` JSON endpoint gives the UI a stable selector (`body`) and value templates for temperature,
memory usage, storage usage, Tailscale IPv4, all IPv4 addresses, and host battery charging status.
No Home Assistant YAML, HACS, automations, or changes to the Home Assistant configuration repository
are introduced.

The design avoids host networking, host PID sharing, privileged mode, host ports, ingress, and
secrets. Host access is read-only, the container runs as a non-root user with all capabilities
dropped, and the exporter is stateless so pod restarts and node reboots recover through normal
GitOps reconciliation.

## Technical Context

**Language/Version**: Python 3.12 (standard library only) for the exporter; Kubernetes YAML and
Kustomize v5.8.1 for delivery.

**Primary Dependencies**: `python:3.12-alpine` pinned by digest; Kubernetes k3s
`v1.36.5+k3s1`; Flux Kustomization; Home Assistant's built-in Scrape integration. No third-party
Python packages, no Helm, no HACS.

**Storage**: None. The exporter is stateless. The script is a Kustomize ConfigMap generated from
`apps/host-metrics/exporter.py`. Host data is read through read-only hostPath mounts and never
written.

**Testing**: Python `unittest` for meminfo, route, fib-trie, temperature-selection, usage, and
rendering logic; `scripts/validate.sh` for Kustomize rendering, kubeconform, yamllint, secret scan,
and the new unit tests; cluster verification for readiness, endpoint reachability, metric presence,
Home Assistant UI sensors, pod restart, node reboot, and absence of external exposure.

**Target Platform**: Single amd64 node `dietpi` running DietPi 10.8.2 / Debian 13 / k3s
`v1.36.5+k3s1`. The exporter image supports multi-arch, but only amd64 is required.

**Project Type**: GitOps-managed Kubernetes workload plus a single-file HTTP exporter and operator
documentation.

**Performance Goals**: Each `/metrics` or `/ha` collection completes in under 1 second and reads
only small procfs/sysfs files plus one `statvfs` call. Memory stays well below 64 MiB and CPU below
50 millicores in normal operation. Home Assistant polls every 10 minutes because the UI-only Scrape
integration does not expose a scan interval.

**Constraints**: ClusterIP only; no Ingress, Tailscale ingress, load balancer, node port, host
port, host networking, or host PID namespace; no privileged container; no secret; non-root UID
65534; read-only root filesystem; all Linux capabilities dropped; read-only host mounts; no Home
Assistant repository changes; no Prometheus, Grafana, alerting, or long-term storage.

**Scale/Scope**: One node, one exporter replica, one Service, five host measurement families
(temperature, memory, root filesystem, IPv4 addresses, and battery charging status), and one
documented Home Assistant UI flow.

## Constitution Check

*GATE: Passed before Phase 0 research; re-checked after Phase 1 design.*

| Principle | Result | Evidence |
| --------- | ------ | -------- |
| I. GitOps as source of truth | PASS | Namespace, ConfigMap, Deployment, Service, tests, and docs are committed and reconciled by the existing Flux `apps` Kustomization. No manual `kubectl apply` is required. |
| II. Reproducible host bootstrap | PASS | `docs/11-host-metrics.md` documents the host paths, image digest, endpoint, UI steps, verification, and recovery. A rebuilt host needs only the same k3s/Flux baseline. |
| III. Public repositories, private state | PASS | No secrets, kubeconfigs, state bundles, backups, or real tailnet identifiers. IPv4 values are runtime data, never committed. Documentation uses placeholders. |
| IV. Local-first, documented cloud dependencies | PASS | Exporter and Home Assistant run locally. The only new cloud dependency is pulling the digest-pinned Python image from Docker Hub; its failure mode and local degradation are documented. |
| V. Recoverability before optimization | PASS | The exporter is stateless. Pod restart, node reboot, and missing metric sources have documented recovery and degradation behavior. |
| VI. Small, reviewable, validated changes | PASS | One app directory, one script, two manifests, focused tests, and documentation. `scripts/validate.sh` is extended and the image is digest-pinned. |
| VII. Clear repository boundaries | PASS | This repository owns the exporter, Service, docs, and cluster resources. Home Assistant configuration remains untouched; only UI steps are documented. |
| Technology standards | PASS with justified deviation | Kustomize is used, no Helm is introduced, and the runtime image is digest-pinned. The official upstream Python image is used instead of a first-party GHCR image; see Complexity Tracking. |

**Post-design re-check**: PASS. Phase 1 artifacts consistently preserve ClusterIP-only exposure,
read-only host access, non-root execution, no secrets, no Home Assistant YAML, and no Prometheus
stack.

## Project Structure

### Documentation (this feature)

```text
specs/002-host-metrics-exporter/
├── plan.md              # This file
├── research.md          # Phase 0 decisions and alternatives
├── data-model.md        # Host snapshot, readings, endpoint models, sensor mapping
├── quickstart.md        # Deploy, UI, recovery, and verification scenarios
├── contracts/
│   ├── exporter-api.md  # HTTP endpoints, metric names, labels, units, JSON schema
│   └── home-assistant-ui.md # Exact Scrape UI fields and templates
└── checklists/
    └── requirements.md  # Specification quality checklist
```

### Source Code (repository root)

```text
apps/
├── kustomization.yaml                 # add host-metrics
└── host-metrics/
    ├── kustomization.yaml             # resources + configMapGenerator(exporter.py)
    ├── namespace.yaml                 # monitoring
    ├── deployment.yaml                # single replica, nodeSelector dietpi, probes, security
    ├── service.yaml                   # ClusterIP :9100
    ├── exporter.py                    # Python 3.12 stdlib exporter
    └── test_exporter.py               # parser, selection, and contract unit tests

docs/
├── 11-host-metrics.md                 # operator metric contract, HA UI, recovery
├── 09-limitations.md                  # add exporter-specific limits
└── README.md                          # add document 11 to the index

README.md                              # status, architecture, docs table
scripts/
└── validate.sh                        # add host-metrics unit tests
```

**Structure Decision**: Follow the existing `apps/<name>/` pattern used by `apps/home-assistant`.
The exporter is a workload, so it belongs under `apps/`, not `infrastructure/`. The `monitoring`
namespace is declared with the workload, matching the Home Assistant namespace pattern. The script
is kept as a standalone Python file and injected with `configMapGenerator`, so it stays reviewable
and testable rather than being embedded in YAML. The Deployment references the generated ConfigMap
by name; Kustomize rewrites the reference to the hash-suffixed name, and a script change rolls the
pod on the next reconciliation.

## Design Decisions

### Exporter implementation

Use a custom Python 3.12 standard-library exporter rather than Node Exporter plus a textfile
sidecar. Node Exporter covers temperature, memory, and filesystem metrics but does not expose host
IPv4 addresses; its network address collector enumerates the container network namespace unless
host networking is used, which this feature forbids. The custom exporter also reads the host
`power_supply` battery status, provides the JSON projection needed by the UI-only Home Assistant
integration, and avoids a second process, a shared textfile volume, and a fragile Prometheus-text
parser in Home Assistant.

### Host access

Mount only what is needed, read-only:

| Host path | Container path | Purpose |
| --------- | -------------- | ------- |
| `/proc/meminfo` | `/host/proc/meminfo` | Memory total and available |
| `/proc/1/net` | `/host/proc/1/net` | Host network namespace `fib_trie` and route table, without host networking or host PID sharing |
| `/sys` | `/host/sys` | hwmon and thermal-zone temperature sources, plus `power_supply` battery status |
| `/` | `/host/root` | `statvfs` for the filesystem mounted at `/` |

The container does not set `hostNetwork`, `hostPID`, `hostIPC`, `hostPort`, or `privileged`. The
pod runs as UID/GID 65534 with `runAsNonRoot: true`, `allowPrivilegeEscalation: false`,
`readOnlyRootFilesystem: true`, `capabilities.drop: ["ALL"]`, and
`automountServiceAccountToken: false`. The root mount is the broadest host exposure; it is
read-only, and the script only calls `statvfs` on it. This trade-off is documented in
`docs/11-host-metrics.md` and `docs/09-limitations.md`.

### Metrics and Home Assistant contract

The exporter serves:

- `GET /metrics` — Prometheus text, gauge families for temperature, memory, filesystem, IPv4 info,
  and battery status info.
- `GET /ha` — flat JSON projection consumed by Home Assistant's Scrape UI, including
  `battery_status`.
- `GET /healthz` — liveness, 200 while the process is serving HTTP.
- `GET /readyz` — readiness, 200 only when memory and root filesystem collection succeed.

Exact names, labels, units, JSON keys, and failure behavior are fixed in
`contracts/exporter-api.md`. The Home Assistant UI fields and templates are fixed in
`contracts/home-assistant-ui.md`.

### Battery status

Battery status comes from Linux `power_supply` devices whose `type` file is `Battery`. The exporter
reads each device's `status` file under `/host/sys/class/power_supply/<device>/status` through the
existing read-only `/sys` mount. It exposes one info metric per battery and a flat
`battery_status` key for the deterministic preferred battery, plus a `battery_statuses` array for
all batteries. The raw kernel string is preserved (`Charging`, `Discharging`, `Full`, `Not
charging`, `Unknown`); no binary mapping is invented. If there is no battery, the metric family is
omitted, `battery_status` is null, and the Home Assistant sensor's availability template makes it
unavailable. This adds no NUT/UPS service, USB access, privilege, or secret.

### Deployment shape

- One replica, `nodeSelector: {kubernetes.io/hostname: dietpi}`, and a control-plane toleration so
  the pod remains schedulable if the single control-plane node ever carries a taint.
- Container port `9100` named `http`.
- Startup probe and readiness probe on `/readyz`; liveness probe on `/healthz`.
- Requests: `cpu: 10m`, `memory: 32Mi`. Limits: `cpu: 100m`, `memory: 96Mi`.
- `automountServiceAccountToken: false`; no ServiceAccount, RBAC, Secret, or PersistentVolumeClaim.

### Exposure

A single ClusterIP Service on port 9100 selects the exporter. There is no Ingress, Tailscale
ingress, load balancer, node port, host port, or host networking. The cluster has no working
NetworkPolicy layer for this path (k3s/kube-router network policies are disabled per
`docs/09-limitations.md`), so the Service is reachable from any pod in the cluster; it is not
reachable from outside the cluster. This namespace-level trust boundary is documented.

### Home Assistant integration

Use the built-in Scrape integration, configured through the UI, with the resource
`http://host-metrics.monitoring.svc.cluster.local:9100/ha`. Each sensor uses `select: body` and a
JSON `value_template`, an availability template for optional values, and the documented unit,
device class, and state class. The Scrape UI does not expose a scan interval and polls every 10
minutes; that cadence is documented as a limitation. No Home Assistant YAML, HACS, or automation is
added.

## Security Trade-offs

| Trade-off | Reason | Mitigation |
| --------- | ------ | ---------- |
| Read-only host `/` mount | Exact `statvfs("/")` requires a path on the root filesystem; mounting a subdirectory could report a different filesystem after a host layout change. | Read-only; non-root; no host write; script only calls `statvfs`; no untrusted input is executed. |
| Read-only host `/sys` mount | hwmon entries are symlinks under `/sys/class/hwmon` that resolve into `/sys/devices`; mounting only the class directory breaks the links. The same mount supplies `power_supply` battery status. | Read-only; non-root; only hwmon temperature files and `power_supply/*/type` plus `power_supply/*/status` are read. |
| `/proc/1/net` mount | Host IPv4 addresses must be read without host networking; the host network namespace is the only source. | Narrow procfs mount; no host PID namespace; no `nsenter`; no capabilities. |
| ClusterIP reachable from all pods | NetworkPolicy is not reliable on this k3s/kube-router node. | Cluster-internal only; no ingress; no external address; namespace trust is documented. |
| Upstream Python image from Docker Hub | Avoids a first-party build and image-automation pipeline for a single script. | Digest-pinned, public, minimal Alpine image; Docker Hub failure mode documented; no secret in the image. |

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
| --------- | ---------- | ------------------------------------- |
| First-party GHCR image standard is not used; the exporter runs from the official `python:3.12-alpine` image pinned by digest. | The deployable code is a small Git-tracked script. A runtime image is sufficient; the script, not an image layer, is the reviewable artifact. Digest pinning preserves immutability. | Building and publishing a GHCR image adds a workflow, package permissions, a tag policy, image automation, and a second place to update for a ~200-line script. It adds operational surface without improving the feature contract. The Docker Hub dependency is documented and degrades locally. |

## Verification Plan

1. **Static validation**: `scripts/validate.sh` renders `apps/` and `infrastructure/`, validates
   schemas, lints YAML, scans for secrets, and runs the exporter unit tests.
2. **Flux reconciliation**: `flux get kustomizations apps` is Ready; the `monitoring` namespace
   contains the ConfigMap, Deployment, and Service; the pod is Ready on `dietpi`.
3. **Endpoint contract**: From the `home-assistant` namespace, `/metrics` returns HTTP 200 and
   contains every required family; `/ha` returns the documented JSON keys; `/readyz` returns 200.
4. **Exposure check**: Service type is `ClusterIP`; no Ingress references the exporter; Deployment
   has no `hostNetwork`, `hostPID`, `hostPort`, or `privileged`; no NodePort or LoadBalancer.
5. **Home Assistant UI**: Follow `contracts/home-assistant-ui.md` to create temperature, memory
   usage, storage usage, Tailscale IPv4, all-IPv4, and battery-status sensors. Verify values in
   Developer Tools > States and observe an update after the 10-minute poll or an exporter restart.
6. **Restart**: Delete the exporter pod; the Deployment recreates it, `/metrics` returns within 2
   minutes, and Home Assistant sensors recover at the next poll without reconfiguration.
7. **No temperature sensor**: Unit tests cover the absent-source path; on the host, the exporter
   reports `temperature_c: null`, exposes the other families, and the temperature sensor's
   availability template makes it unavailable rather than zero.
8. **Battery status**: When a host battery exists, `/metrics` contains
   `host_battery_status_info` and `/ha` contains `battery_status`; the Home Assistant sensor shows
   the raw kernel state. When no battery exists, the family is absent, `battery_status` is null,
   and the sensor is unavailable. Multiple batteries are exposed with device labels and the
   preferred battery is deterministic.
9. **Node reboot**: After a coordinated reboot, Flux reconciles the workload, the pod is Ready on
   `dietpi`, the endpoint is reachable, and IPv4 and battery values reflect the current interfaces
   and power state.
10. **Failure behavior**: With the exporter down, Home Assistant sensors become unavailable; with
    a missing host path, the pod is not Ready and logs the cause; with an unreadable hwmon or
    `power_supply/*/status` file, only that reading is absent while the other families continue to
    be served.
