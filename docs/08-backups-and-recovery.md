# 08 — Backups and recovery

Status: procedures documented; drills are executed after Phase 4.

## What must survive

| Asset | Where it lives | Recovery source |
| ----- | -------------- | --------------- |
| Cluster and workload manifests | Git | `home-sweet-lab` |
| Home Assistant tracked YAML | Configuration repository and image | `home-sweet-home-home-assistant` |
| Home Assistant private state | PVC | State bundle and Home Assistant backups |
| Home Assistant backups | PVC `/config/backups` | Pulled copies on the Mac and offsite storage |
| k3s datastore | DietPi `/var/lib/rancher/k3s/server/db` | Cold copy on the host or external disk |
| Manual Kubernetes Secrets | Cluster | Password manager |
| kubeconfig and Tailscale auth | Operator devices | Regenerate / re-enroll |

Git is not a backup of household state. The PVC is not a backup either: it is the live copy.

## Targets

| Measure | Target |
| ------- | ------ |
| Recovery point objective | Last successful Home Assistant backup and last pulled copy |
| Recovery time objective | Under 60 minutes for a full cluster rebuild plus state restore |
| Backup verification | Checksum matched and a restore exercised at least quarterly |

## Pull backups to the Mac

Home Assistant writes backups to `/config/backups` on the PVC. Pull them deliberately.

With the pod running:

```bash
mkdir -p ~/backups/home-sweet-lab
pod="$(kubectl -n home-assistant get pods -o jsonpath='{.items[0].metadata.name}')"
kubectl -n home-assistant cp \
  "$pod:/config/backups/." \
  "$HOME/backups/home-sweet-lab/"
```

If `kubectl cp` fails because the container lacks `tar`, use a helper pod or stream a tar:

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  tar -C /config/backups -czf - . > "$HOME/backups/home-sweet-lab/backups-$(date +%Y%m%d-%H%M%S).tar.gz"
```

Verify every archive before trusting it:

```bash
cd "$HOME/backups/home-sweet-lab"
shasum -a 256 ./*.tar.gz > SHA256SUMS
shasum -a 256 -c SHA256SUMS
```

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
3. Upload the newest state bundle to a helper pod on the new PVC.
4. Restart Home Assistant and watch the `restore-state` init container.
5. If the bundle is incomplete, restore a Home Assistant backup from the UI instead.

### Full cluster rebuild

1. Follow [01-hardware-and-dietpi.md](01-hardware-and-dietpi.md) through
   [05-flux-bootstrap.md](05-flux-bootstrap.md).
2. Confirm Flux reconciles `home-sweet-lab`.
3. Recreate manual Secrets.
4. Apply the PVC and upload the newest state bundle.
5. Start Home Assistant and verify integrations, ZHA, dashboards, and automations.
6. Pull a fresh backup and verify it.

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

## Drill checklist

Run these on the real cluster, not in theory:

- [ ] Delete the Home Assistant pod with the PVC intact; it returns without data loss.
- [ ] Create a state bundle, upload it to a scratch PVC, and verify the restore.
- [ ] Corrupt a bundle checksum; confirm the restore refuses and the workload still starts.
- [ ] Pull a backup, verify its checksum, and restore it through the Home Assistant UI.
- [ ] Simulate a missing ZBT-2; confirm the failure is visible and recoverable after reconnecting.
- [ ] Rebuild the cluster from documentation in under 60 minutes.
- [ ] Confirm no secret, kubeconfig, bundle, or backup exists in either public repository.

## Automation is future work

A CronJob or Home Assistant automation that creates and offsites backups is desirable but out of
scope for v1. Until then, the pull is manual and must be recorded. Manual does not mean optional.
