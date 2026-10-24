# 07 — Secrets and unsynced state

Status: procedure documented; scripts land in Phase 5.

Both repositories are public. Git contains only configuration that is safe to publish. Everything
else lives on the persistent volume and moves through explicit, documented operations.

## What lives where

| Path | Content | Handling |
| ---- | ------- | -------- |
| Tracked YAML | `configuration.yaml`, automations, scripts, scenes, dashboards | Built into the image from the configuration repository |
| `blueprints/` | Downloaded or manually added blueprints | PVC only; state bundle |
| `.storage/` | Integration credentials, entity registry, UI-managed dashboards, ZHA config | PVC only; state bundle |
| `secrets.yaml` | Home Assistant `!secret` values | PVC only; state bundle; never Git |
| `zigbee.db` | Zigbee network state | PVC only; state bundle |
| `home-assistant_v2.db*` | History and recorder database | PVC only; state bundle |
| `backups/` | Home Assistant backup archives | PVC only; pulled to the Mac |
| `media/`, `tts/`, `www/community/` | Local media, generated TTS, HACS assets | PVC only; state bundle |
| `home-assistant.log*`, `.cache/`, `deps/` | Logs and regenerable caches | Not backed up |
| Kubernetes Secrets | Future cluster credentials | Manual `kubectl`; never Git |

The current Home Assistant configuration has no `secrets.yaml`; verify before assuming one exists.
`.storage` still contains integration credentials and must be treated as secret.

## Manual Kubernetes Secrets

Flux does not manage Secrets in v1. Create them directly and record their purpose here.

```bash
kubectl create namespace home-assistant --dry-run=client -o yaml | kubectl apply -f -
kubectl -n home-assistant create secret generic home-assistant-secrets \
  --from-file=secrets.yaml=/path/to/home-assistant/secrets.yaml
```

If Home Assistant consumes `secrets.yaml` from disk, mount the Secret as a file rather than copying
it into the image:

```yaml
volumeMounts:
  - name: ha-secrets
    mountPath: /config/secrets.yaml
    subPath: secrets.yaml
    readOnly: true
volumes:
  - name: ha-secrets
    secret:
      secretName: home-assistant-secrets
```

Alternatively, keep `secrets.yaml` on the PVC via the state bundle. Do not do both with different
contents; pick one and document it.

Rules:

- Never commit a Secret manifest with plaintext data, even briefly.
- Never commit a `kubectl` command that embeds a credential value.
- Record the Secret name, namespace, purpose, and rotation owner in this document.
- After a cluster rebuild, recreate manual Secrets before expecting the workload to work.
- Drift is expected because Flux cannot reconcile them. Audit at each recovery drill.

## State bundle

The bundle is the supported way to move private state between the Mac and the cluster. It is a
`tar.gz` archive plus a checksum.

### Default contents

- `.storage/`
- `secrets.yaml` (if present)
- `zigbee.db`
- `blueprints/`
- `backups/`
- `home-assistant_v2.db`, `home-assistant_v2.db-wal`, `home-assistant_v2.db-shm`
- `media/`
- `tts/`
- `www/community/`

Excluded: tracked YAML, logs, `.cache/`, `deps/`, and anything already in the image.

### Create

Stop Home Assistant before creating a bundle so `.storage` and SQLite are consistent:

```bash
# Old Mac deployment
docker compose stop home-assistant
```

Until `scripts/create-state-bundle.sh` exists, use an equivalent shell block:

```bash
bundle="home-assistant-state-$(date +%Y%m%d-%H%M%S).tar.gz"
paths=()
for p in .storage secrets.yaml zigbee.db blueprints backups \
         home-assistant_v2.db home-assistant_v2.db-wal home-assistant_v2.db-shm \
         media tts www/community; do
  [ -e "config/$p" ] && paths+=("$p")
done
tar -czf "$bundle" -C config "${paths[@]}"
# macOS
shasum -a 256 "$bundle" | awk '{print $1}' > "$bundle.sha256"
# Linux
# sha256sum "$bundle" | awk '{print $1}' > "$bundle.sha256"
ls -lh "$bundle" "$bundle.sha256"
```

The checksum file contains the hash in its first field. The restore step compares that value before
extracting.

Restart the old deployment if it is still in service:

```bash
docker compose start home-assistant
```

### Upload

Create a temporary pod that mounts the PVC, copy the archive into `/config/import/`, then delete the
pod. The namespace and PVC must already exist.

```bash
kubectl -n home-assistant apply -f - <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: ha-upload
spec:
  restartPolicy: Never
  containers:
    - name: upload
      image: alpine:3.20
      command: ["sh", "-c", "sleep 3600"]
      volumeMounts:
        - name: config
          mountPath: /config
  volumes:
    - name: config
      persistentVolumeClaim:
        claimName: home-assistant-config
EOF

kubectl -n home-assistant wait --for=condition=Ready pod/ha-upload --timeout=120s
kubectl -n home-assistant exec ha-upload -- mkdir -p /config/import
kubectl -n home-assistant cp ./home-assistant-state-<timestamp>.tar.gz \
  ha-upload:/config/import/
kubectl -n home-assistant cp ./home-assistant-state-<timestamp>.tar.gz.sha256 \
  ha-upload:/config/import/
kubectl -n home-assistant delete pod ha-upload
```

Restart Home Assistant so the restore init container runs:

```bash
kubectl -n home-assistant rollout restart deployment/home-assistant
kubectl -n home-assistant rollout status deployment/home-assistant --timeout=10m
kubectl -n home-assistant logs deploy/home-assistant -c restore-state
```

If Flux manages the Deployment and a rollout restart would be reverted, use
`kubectl delete pod -n home-assistant -l app.kubernetes.io/name=home-assistant` instead; the
ReplicaSet recreates it and the init containers run again.

### Restore behavior

- The script verifies the checksum before touching `/config`.
- A mismatch or extraction failure exits non-zero and leaves the archive in `/config/import/` for
  inspection.
- Applied archives move to `/config/import/applied/` and are not re-applied on the next restart.
- To apply a new bundle, upload it with a new filename. To re-apply the same content, upload it
  under a new name or remove its marker from `applied/` deliberately.
- Keep at least the previous bundle until the new state has been verified.

### Never commit

`*.tar`, `*.tar.gz`, `*.tgz`, `*.zip`, `bundles/`, `backups/`, and `secrets/` are ignored. Do not
override those rules. A bundle contains credentials, device keys, and household history.

## Manual edits are temporary

The image seed overwrites tracked YAML at every start. If a tracked file is edited on the server, the
edit disappears at the next pod restart. Make the change in the configuration repository instead.

Untracked files on the PVC are not overwritten by the seed and are safe to edit manually, but they
are also not backed up unless they are part of a bundle or a Home Assistant backup.

## Rotation checklist

1. Rotate the credential at the source.
2. Update the manual Secret or the state file on the PVC.
3. Restart the workload.
4. Verify the integration or service.
5. Revoke the old credential.
6. Record the date and owner in this document.
