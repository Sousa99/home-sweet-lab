# 09 — Limitations and future work

These are deliberate v1 boundaries. They are documented so they are not mistaken for oversights.

## Access and TLS

- Home Assistant is served with HTTPS at `https://home-assistant.<tailnet>.ts.net/`. The Tailscale
  Kubernetes Operator creates the proxy device, the MagicDNS name, and a Tailscale-issued
  certificate.
- The certificate covers the Tailscale hostname only. It is not a public certificate; access is
  limited to tailnet devices.
- The operator is an additional controller and a cloud dependency. If the operator or its ingress
  proxy is down, the Home Assistant URL is unavailable, although the Home Assistant pod and local
  automations keep running.
- The OAuth client used by the operator is a manual Secret. It must be recreated after a cluster
  rebuild and rotated deliberately.
- The host's Traefik still binds ports 80 and 443. Do not enable Tailscale Serve on the host while
  Traefik holds those ports; the operator does not use host ports.
- The root URL `http://dietpi/` no longer serves Home Assistant. It is available for a future
  landing page or other apps.
- The k3s API certificate includes the host Tailscale IP and short hostname, not the host MagicDNS
  FQDN. Use the IP in kubeconfig or add the FQDN to `tls-san` and restart k3s.
- Tailscale is a cloud dependency for coordination, remote access, and certificates. Zigbee control,
  automations, and local Home Assistant operation continue if it is unavailable.

## Single node and storage

- One control-plane node. No high availability, no failover, no maintenance window without downtime.
- `local-path` storage is a directory on the node's NVMe. It is not replicated, not snapshotted, and
  uses `ReclaimPolicy: Delete`.
- Volume expansion is not supported. Resizing means a new PVC and a restore.
- Disk failure, filesystem corruption, or accidental PVC deletion loses live state. Recovery depends
  on backups and state bundles.
- The NVMe is the only disk. There is no separate data disk and no RAID.
- No UPS. An unclean shutdown can corrupt SQLite databases.

## Host security

- No host firewall is installed. Dropbear listens on all interfaces on 22 and the k3s API listens on
  all interfaces on 6443.
- Tailscale ACLs are the primary remote-access control. If the host joins an untrusted LAN, add a
  host firewall and restrict access to the tailnet interface.
- Flux's Kubernetes NetworkPolicies are disabled. On this single-node k3s installation, kube-router
  left stale default-deny pod firewall rules that blocked controller-to-controller traffic. Pod
  traffic inside the cluster is therefore unrestricted; namespace separation and Tailscale ACLs are
  the boundary.
- The `dietpi` user has passwordless `sudo`. Protect the account and prefer key-based SSH.
- SSH password authentication is enabled by default. Disable it after key-based access works.
- The Home Assistant container runs `privileged: true` to access the ZBT-2. This is broader than a
  device-specific permission and should be narrowed when practical.
- The host timezone is UTC; Home Assistant uses `Europe/Lisbon`. Set the host timezone for consistent
  logs.

## Secrets

- Kubernetes Secrets are created manually and are not reconciled by Flux. Drift is expected.
- `.storage` contains integration credentials on the PVC; the PVC is not encrypted at rest.
- `secrets.yaml` may not exist yet. If it is added, it must be delivered through the PVC or a
  manually created Secret, never through Git.
- There is no external secret manager, SOPS, Sealed Secrets, or automatic rotation.
- State bundles and backups contain credentials and household data. Their handling is manual and
  must be encrypted when stored offsite.

## State and backups

- State migration and backup pulls are manual. Manual does not mean optional.
- There is no automated offsite backup. The recovery point objective is the last pulled copy.
- Home Assistant backups live on the same NVMe as the live state until pulled.
- The state bundle is a transport mechanism, not a snapshot system. Creating one while Home
  Assistant is running risks inconsistent SQLite or `.storage` data.
- The restore init container verifies a checksum but does not make extraction atomic. A failure
  mid-extraction can leave partial state; keep the previous bundle and a backup.
- A restored `.storage` from the Mac still points ZHA at the old RFC2217 bridge until reconfigured.

## Workload behavior

- No mDNS/multicast discovery because the pod uses cluster networking. HomeKit, Google Cast, and
  some discovery-based integrations may need `hostNetwork: true` or additional configuration.
- Ingress is path-based at `/` for v1. There is no host-based virtual hosting or TLS.
- Home Assistant tracks the `stable` base image. Major upgrades can arrive without a deliberate
  version bump. Back up before upgrades and consider pinning a digest.
- The ZBT-2 is a single coordinator and a single point of failure for Zigbee.
- If the device is absent, Home Assistant can start but ZHA is unavailable. Decide whether a missing
  coordinator should block startup.
- The image contains tracked YAML only. Manual edits to tracked files on the server are overwritten
  at the next pod start.
- Home Assistant 2026.8+ stores HTTP server settings in `.storage/http` and deprecates the `http:`
  block in `configuration.yaml`. The cluster enforces reverse-proxy trust through an init container;
  do not re-add the YAML block.
- The GHCR package must stay public or the cluster needs an image pull secret.
- Flux image automation needs a read-write deploy key; a read-only bootstrap key silently prevents
  image tag write-back.

## Host metrics exporter and MQTT device

- The exporter is visibility only. It is not an availability monitor, an alerting system, or a
  long-term metrics store.
- The primary Home Assistant path is MQTT discovery, producing one `home-sweet-lab-server` device
  with six entities. The legacy Scrape path polls every 10 minutes; the MQTT path publishes every
  30 seconds. See [`12-host-metrics-mqtt.md`](12-host-metrics-mqtt.md).
- The host may have no battery or no usable temperature sensor. In that case the corresponding
  per-source availability topic goes offline, the entity is unavailable, and the other entities
  continue to work. The exporter does not fabricate a value.
- Battery status is the raw Linux `power_supply` state (`Charging`, `Discharging`, `Full`, `Not
  charging`, or `Unknown`). Battery percentage, health, runtime, and NUT/UPS integration are out of
  scope.
- The exporter reads `/proc/meminfo`, `/proc/1/net`, `/sys`, and `/` through read-only hostPath
  mounts. The host `/` mount is the broadest exposure; it exists only for `statvfs("/")`. The
  container runs as UID/GID 65534 with all capabilities dropped and no privileged mode.
- `/proc/1/net` is a narrow read of the host network namespace. The exporter does not use
  hostNetwork or the host PID namespace.
- The exporter image is built in this repository and published to GHCR. The broker uses the pinned
  `eclipse-mosquitto:2` image. Docker Hub and GHCR are image dependencies; if an image is
  unavailable and not cached, the affected pod cannot start. Home Assistant and other workloads are
  unaffected.
- Mosquitto runs in `monitoring` with a ClusterIP Service on 1883. It uses two MQTT users and
  topic ACLs. The credentials are a manual Secret, never committed.
- MQTT is plain TCP inside the cluster. There is no MQTT TLS in v1. Auth and ACLs are the boundary;
  the broker is not externally exposed.
- The broker is ephemeral: no PVC, and retained discovery/state is lost on broker restart. The
  exporter republishes on reconnect and on the Home Assistant birth message.
- If the exporter is down, the broker publishes the Last Will and all MQTT entities become
  unavailable. They recover automatically after the exporter is Ready again.
- If the broker is down, MQTT entities become unavailable. The exporter reconnects when the broker
  returns. There is no alert; check `kubectl -n monitoring` and the Home Assistant UI manually.
- The cluster has no reliable NetworkPolicy layer, so any pod can reach the exporter and broker;
  neither is reachable from outside the cluster.
- The exporter does not add IPv6 reporting, network throughput, disk I/O, per-container metrics, or
  external access. The Kubernetes node, hostname, Linux user, and OS remain `dietpi`; only the Home
  Assistant device identity is `home-sweet-lab-server`.

## Operations

- No Prometheus, Grafana, alerting, log aggregation, or dashboarding beyond Lens, `kubectl`, the
  internal host-metrics exporter, and the MQTT device.
- No automated certificate rotation, datastore backup, or configuration drift detection.
- No SSO for Home Assistant; household accounts are managed in the Home Assistant UI.
- Recovery drills are manual and must be scheduled.
- k3s and kube-router have required a service sync restart and a node reboot after network policy
  changes. Treat network policy changes as maintenance-window work and verify controller traffic
  afterward.
- The other `home-sweet-home-*` workloads (agent, dashboard, modules) are not migrated in v1.

## Future work, roughly ordered

1. Pull backups off the node automatically and verify them.
2. Add monitoring and alerting for node, Flux, PVC, and Home Assistant.
3. Add a landing page or dashboard at `/`.
4. Add a secret manager or SOPS with age for reproducible secrets, including `operator-oauth`.
5. Narrow device access instead of `privileged: true`.
6. Pin the Home Assistant base image and test upgrades deliberately.
7. Move other household workloads into the cluster.
8. Evaluate replicated storage and a second node only if the household needs high availability.
9. Re-enable Flux network policies after verifying k3s/kube-router behavior on this node.
