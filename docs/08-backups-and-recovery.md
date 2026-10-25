# 08 — Backups and recovery

Status: pull script implemented; drills executed on 2026-10-25.

## What must survive

| Asset | Where it lives | Recovery source |
| ----- | -------------- | --------------- |
| Cluster and workload manifests | Git | `home-sweet-lab` |
| Home Assistant tracked YAML | Configuration repository and image | `home-sweet-home-home-assistant` |
| Home Assistant private state | PVC | State bundle and Home Assistant backups |
| Home Assistant backups | PVC `/config/backups` | Pulled copies on the Mac and offsite storage |
| k3s datastore | DietPi `/var/lib/rancher/k3s/server/db` | Cold copy on the host or external disk |
| Manual Kubernetes Secrets | Cluster | Password manager |
| Tailscale operator OAuth client | Cluster `operator-oauth` Secret and Tailscale admin console | Password manager / Tailscale admin console |
| kubeconfig and Tailscale auth | Operator devices | Regenerate / re-enroll |

Git is not a backup of household state. The PVC is not a backup either: it is the live copy.

## Targets

| Measure | Target |
| ------- | ------ |
| Recovery point objective | Last successful Home Assistant backup and last pulled copy |
| Recovery time objective | Under 60 minutes for a full cluster rebuild plus state restore |
| Backup verification | Checksum matched and a restore exercised at least quarterly |

## Pull backups to the Mac

Home Assistant writes backups to `/config/backups` on the PVC. Pull them with:

```bash
cd ~/Desktop/code/home-sweet-lab
./scripts/pull-backups.sh
```

The default destination is `~/backups/home-sweet-lab/<timestamp>`. Override it with `--dest DIR`.
The script uses the running Home Assistant pod, or creates a temporary helper pod if Home Assistant is
stopped. It writes `SHA256SUMS` and verifies every file.

On 2026-10-25 the drill pulled five files and all checksums matched:

```text
~/backups/home-sweet-lab/20261025-drill/
├── Automatic_backup_*.tar
├── README.md
└── SHA256SUMS
```

The PVC currently contains the pre-migration backup archives copied from the Mac. Create a fresh
backup from the Home Assistant UI or an automation before relying on the current set.

Keep at least one copy outside the house, encrypted. A backup on the same NVMe as the live state is
not disaster recovery.

## Home Assistant backup policy

For v1:

- Create a backup before every configuration or image change.
- Create a periodic backup (weekly minimum) from the Home Assistant UI or an automation.
- Pull the latest backup to the Mac after each significant change.
- Record the last successful pull date.

Backups contain credentials, device keys, and household data. Never commit them and never upload them
to a public artifact store.

## Restore procedures

### Pod lost, volume intact

Flux or the ReplicaSet recreates the pod. The PVC keeps `.storage`, databases, and backups. No
restore is needed.

```bash
kubectl -n home-assistant get pods
kubectl -n home-assistant rollout status deployment/home-assistant --timeout=10m
```

### Volume lost

1. Confirm the PVC is gone or unusable:

   ```bash
   kubectl -n home-assistant get pvc
   kubectl -n home-assistant describe pvc home-assistant-config
   ```

2. Let Flux recreate the PVC, or apply `apps/home-assistant/pvc.yaml`.
3. Upload the newest state bundle with `scripts/upload-state-bundle.sh`.
4. Restart Home Assistant and watch `restore-state` and `configure-http`.
5. If the bundle is incomplete, restore a Home Assistant backup from the UI instead.

### Full cluster rebuild

1. Follow [01-hardware-and-dietpi.md](01-hardware-and-dietpi.md) through
   [05-flux-bootstrap.md](05-flux-bootstrap.md).
2. Recreate the Tailscale `operator-oauth` Secret in the `tailscale` namespace before Flux installs
   the operator. Create a new OAuth client if the old credentials are unavailable.
3. Confirm Flux reconciles `home-sweet-lab` and the Tailscale operator/Ingress become ready.
4. Apply the PVC and upload the newest state bundle.
5. Start Home Assistant and verify integrations, ZHA, dashboards, and automations.
6. Verify `https://home-assistant.<tailnet>.ts.net/` returns `200`.
7. Pull a fresh backup and verify it.

### k3s datastore recovery

Only needed if the cluster API or datastore is corrupted. This is a cold procedure:

```bash
sudo systemctl stop k3s
sudo cp -a /var/lib/rancher/k3s/server/db /root/k3s-db-before-restore-$(date +%Y%m%d-%H%M%S)
sudo rm -rf /var/lib/rancher/k3s/server/db
sudo cp -a /root/k3s-db-backup-<timestamp> /var/lib/rancher/k3s/server/db
sudo systemctl start k3s
```

Confirm the node and Flux return before touching workloads. This restores cluster objects, not Home
Assistant state; the PVC and bundles are separate.

### Broken image or configuration

- Revert the configuration repository commit; CI publishes a new image; Flux updates the Deployment.
- Or pin the previous image tag in `apps/home-assistant/deployment.yaml` and reconcile.
- Do not leave a manual `kubectl set image` as the fix; commit the intended state.

### Lost manual Secret

Recreate it from the password manager, restart the workload, and verify. Record the rotation date in
[07-secrets-and-unsynced-state.md](07-secrets-and-unsynced-state.md).

### Lost Flux installation

Re-run the bootstrap command from [05-flux-bootstrap.md](05-flux-bootstrap.md). The repository
contains the desired state.

## Drill results — 2026-10-25

| Drill | Result |
| ----- | ------ |
| Delete the Home Assistant pod with the PVC intact | Passed: new pod ready in under one minute; `https://home-assistant.<tailnet>.ts.net/` returned `200`; `configure-http` reported already configured |
| Create/upload a state bundle | Passed during migration: bundle applied, retained under `import/applied/` |
| Re-upload the same bundle | Passed: restore reported `already applied` and did not extract again |
| Corrupt bundle checksum | Passed: restore exited non-zero and left the archive in place |
| Archive with `../` path traversal | Passed after hardening: restore refused the archive before extraction |
| Pull backups and verify checksums | Passed: five files pulled; every SHA-256 matched |
| Image automation | Passed: Flux selected and deployed the published tag |
| Tailscale Ingress and TLS certificate | Passed: the operator created the proxy, MagicDNS name, and certificate; HTTPS returned `200` |
| Full PVC loss and restore | Not executed: destructive, requires a maintenance window |
| Full cluster rebuild | Not executed: requires a maintenance window |
| Missing ZBT-2 | Not executed: would disconnect Zigbee; fail-fast behavior is documented |
| Restore a backup through the Home Assistant UI | Not executed: requires UI authentication and a maintenance window |
| Secret scan of both repositories | Passed: `gitleaks` found no leaks |

The full PVC and cluster rebuild drills must be run before treating the recovery time objective as
proven.

## Validation

Run the local checks before merging:

```bash
./scripts/validate.sh
```

This renders the app Kustomization, validates Kubernetes schemas with `kubeconform`, lints YAML with
`yamllint`, and scans for secrets with `gitleaks`. The same checks run in GitHub Actions.

## Automation is future work

A CronJob or Home Assistant automation that creates and offsites backups is desirable but out of
scope for v1. Until then, the pull is manual and must be recorded. Manual does not mean optional.
