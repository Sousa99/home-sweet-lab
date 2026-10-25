# 09 — Limitations and future work

These are deliberate v1 boundaries. They are documented so they are not mistaken for oversights.

## Access and TLS

- Home Assistant is served over HTTP on the tailnet. WireGuard encrypts transit, but the browser
  does not get a secure context.
- Some browser features (clipboard, geolocation, camera APIs) and some Home Assistant integrations
  expect HTTPS. Expect warnings or reduced functionality.
- Tailscale Serve on port 443 conflicts with the Traefik service load balancer. Enabling HTTPS
  requires moving Traefik to port 80, adopting the Tailscale Kubernetes Operator, or adding
  cert-manager with DNS validation.
- MagicDNS provides `<host>.<tailnet>.ts.net` only. Arbitrary subdomains need Tailscale Serve or the
  Operator.
- The k3s API certificate includes the Tailscale IP and short hostname, not the MagicDNS FQDN. Use
  the IP in kubeconfig or add the FQDN to `tls-san` and restart k3s.
- Tailscale is a cloud dependency for coordination and remote access. Local automations, Zigbee, and
  LAN access continue if it is unavailable.

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

## Operations

- No monitoring, alerting, log aggregation, or dashboarding beyond Lens and `kubectl`.
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
3. Decide on TLS: Tailscale Serve with Traefik on 80, or the Tailscale Kubernetes Operator.
4. Add a secret manager or SOPS with age for reproducible secrets.
5. Narrow device access instead of `privileged: true`.
6. Pin the Home Assistant base image and test upgrades deliberately.
7. Move other household workloads into the cluster.
8. Evaluate replicated storage and a second node only if the household needs high availability.
9. Re-enable Flux network policies after verifying k3s/kube-router behavior on this node.
