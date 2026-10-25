# 06 — Home Assistant

Status: deployed and verified on 2026-10-25.

## Current state

| Item | Current |
| ---- | ------- |
| Image | `ghcr.io/sousa99/home-sweet-home-home-assistant:main-20261025084504-004e937` |
| Deployment | 1/1 ready, strategy `Recreate` |
| PVC | `home-assistant-config`, 10 GiB, `Bound` on `local-path` |
| Ingress | Traefik `PathPrefix(/)`, `http://dietpi/` returns `200` |
| HTTP proxy | `.storage/http` trusts `10.42.0.0/16` and `10.43.0.0/16` |
| ZHA | `/dev/zbt2`, 460800, hardware flow control; serial device held by Home Assistant |
| State | Bundle `home-assistant-state-20261025-083605.tar.gz` applied and retained under `import/applied/` |
| Flux | `apps` and `flux-system` Kustomizations `Ready` |

## Model

Home Assistant is deployed from an image built by the public configuration repository
`home-sweet-home-home-assistant`. The image contains tracked YAML only. A persistent volume holds
everything that must not be public: `.storage`, databases, secrets, media, and backups.

```text
home-sweet-home-home-assistant (public)
  config/*.yaml, dashboards
        │ GitHub Actions
        ▼
ghcr.io/sousa99/home-sweet-home-home-assistant:main-<timestamp>-<sha>
        │ Flux image automation
        ▼
home-sweet-lab/apps/home-assistant
  init: seed tracked YAML from /config-seed
  init: restore uploaded state bundle
  HA:   official image + /config PVC + /dev/zbt2
```

Rules:

- The image never contains `.storage`, `secrets.yaml`, databases, backups, logs, or media.
- The init seed copies tracked YAML into `/config` on every start. It never deletes untracked files.
- Editing tracked YAML on the server is temporary; the next pod start overwrites it. Commit instead.
- Untracked state and backups move through explicit bundles; see
  [07-secrets-and-unsynced-state.md](07-secrets-and-unsynced-state.md).

## Image build

In `home-sweet-home-home-assistant`:

```dockerfile
FROM ghcr.io/home-assistant/home-assistant:stable
COPY config/ /config-seed/
COPY scripts/restore-state.sh /usr/local/bin/restore-state.sh
COPY scripts/fix-zha-serial.py /usr/local/bin/fix-zha-serial.py
COPY scripts/fix-http-proxy.py /usr/local/bin/fix-http-proxy.py
RUN chmod 0755 /usr/local/bin/restore-state.sh \
    /usr/local/bin/fix-zha-serial.py \
    /usr/local/bin/fix-http-proxy.py
```

`.dockerignore` must exclude at least:

```text
config/.storage
config/.cloud
config/secrets.yaml
config/backups
config/blueprints
config/home-assistant_v2.db*
config/zigbee.db*
config/home-assistant.log*
config/.HA_VERSION
config/.cache
config/tts
config/media
config/www/community
config/deps
backups
.env
.git
.github
docs
README.md
```

The publish workflow tags images as `main-YYYYMMDDHHMMSS-<sha7>`. The timestamp prefix makes
alphabetical tag ordering match publication order. Do not publish `latest`; do not rely on mutable
tags in the Deployment.

The GHCR package must be public so the cluster can pull it without an image pull secret.

## Kubernetes resources

Planned under `apps/home-assistant/`:

| Resource | Purpose |
| -------- | ------- |
| `namespace.yaml` | `home-assistant` namespace |
| `pvc.yaml` | 10 GiB `local-path` claim mounted at `/config` |
| `deployment.yaml` | Seed init, restore init, Home Assistant container, ZBT-2 mount |
| `service.yaml` | ClusterIP on port 8123 |
| `ingressroute.yaml` | Traefik route from the tailnet address to the service |
| `image-automation.yaml` | Flux image repository, policy, and update automation |
| `kustomization.yaml` | Assembles the app |

### Persistent volume

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: home-assistant-config
  namespace: home-assistant
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: local-path
  resources:
    requests:
      storage: 10Gi
```

This is single-node storage with `ReclaimPolicy: Delete`. The host path is under
`/var/lib/rancher/k3s/storage/`. There are no snapshots. Backups and state bundles are the
recovery mechanism, not the volume.

Size it for the database, media, and retained backups. Increase the request before the volume fills;
`local-path` does not support expansion, so a resize means a new PVC and a restore.

### Init containers

```yaml
initContainers:
  - name: seed-config
    image: ghcr.io/sousa99/home-sweet-home-home-assistant:main-<timestamp>-<sha>
    command: ["sh", "-c", "cp -a /config-seed/. /config/"]
    volumeMounts:
      - name: config
        mountPath: /config

  - name: restore-state
    image: ghcr.io/sousa99/home-sweet-home-home-assistant:main-<timestamp>-<sha>
    command: ["/usr/local/bin/restore-state.sh"]
    env:
      - name: ZHA_SERIAL_PATH
        value: /dev/zbt2
      - name: ZHA_FLOW_CONTROL
        value: hardware
      - name: ZHA_BAUDRATE
        value: "460800"
    volumeMounts:
      - name: config
        mountPath: /config

  - name: configure-http
    image: ghcr.io/sousa99/home-sweet-home-home-assistant:main-<timestamp>-<sha>
    command: ["/usr/local/bin/fix-http-proxy.py"]
    env:
      - name: HTTP_TRUSTED_PROXIES
        value: "10.42.0.0/16,10.43.0.0/16"
    volumeMounts:
      - name: config
        mountPath: /config
```

The restore script:

1. Creates `/config/import/` and `/config/import/applied/`.
2. Walks `/config/import/*.tar.gz`.
3. Verifies the matching `.sha256` before extraction.
4. Rejects absolute paths and `..` path traversal.
5. Extracts into `/config`.
6. Patches ZHA to the cluster serial device through `fix-zha-serial.py`.
7. Moves the archive to `applied/` and records its checksum so restarts do not re-apply it.
8. Exits non-zero on a checksum or extraction failure.

`configure-http` then calls `fix-http-proxy.py` before Home Assistant starts.

### Home Assistant container

- Image: the published configuration image.
- `TZ=Europe/Lisbon`.
- Volume `/config` from the PVC.
- Device `/dev/zbt2` or `/dev/serial/by-id` from the host.
- Port 8123.
- Startup probe on `/manifest.json` with a generous failure threshold; Home Assistant can take
  minutes on first start.
- Liveness and readiness probes on `http://127.0.0.1:8123/manifest.json`.
- `privileged: true` for v1 so the serial device is accessible. Document this as a security
  trade-off; a narrower device cgroup/udev setup is future work.

### Ingress

```yaml
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: home-assistant
  namespace: home-assistant
spec:
  entryPoints: [web]
  routes:
    - match: PathPrefix(`/`)
      kind: Rule
      services:
        - name: home-assistant
          port: 8123
```

Path-based routing is used so no tailnet name is committed and the app is reachable at
`http://dietpi/`. When more apps are added, move to host-based routing with a neutral internal name
or the MagicDNS FQDN, and update this document.

### HTTP proxy configuration (Home Assistant 2026.8+)

Home Assistant 2026.8 deprecated the `http:` block in `configuration.yaml` and now stores HTTP server
settings in `.storage/http`. The YAML block still validates but is ignored at runtime, which produces
a confusing `400` and this log line:

```text
A request from a reverse proxy was received from 10.42.0.x, but your HTTP integration is not set-up for reverse proxies
```

The `configure-http` init container runs `fix-http-proxy.py` before Home Assistant starts. The script
is idempotent and sets:

```json
{
  "use_x_forwarded_for": true,
  "trusted_proxies": ["10.42.0.0/16", "10.43.0.0/16"]
}
```

It also sets `pending` to `null` and `yaml_migration_done` to `true`, and keeps a timestamped backup
of `.storage/http`. Do not add the deprecated `http:` block to `configuration.yaml`; it will be
ignored and may cause a repair issue.

Use the cluster pod CIDR for the Traefik pod. Do not trust arbitrary networks.

## ZBT-2 serial device

The ZBT-2 is already attached to the DietPi host:

| Property | Current |
| -------- | ------- |
| USB ID | `303a:831a` (Nabu Casa ZBT-2) |
| Kernel module | `cdc_acm` |
| Device | `/dev/ttyACM0`, group `dialout`, mode `0660` |
| Stable by-id | `/dev/serial/by-id/usb-Nabu_Casa_ZBT-2_<serial>-if00` |
| Baud / flow control | `460800`, hardware flow control |

Do not commit the full serial number. Retrieve it on the host:

```bash
ls -l /dev/serial/by-id/
udevadm info -q property -n /dev/ttyACM0 | grep -E 'ID_VENDOR_ID|ID_MODEL_ID|ID_SERIAL_SHORT'
```

### Stable symlink

Install the udev rule from `host/dietpi/udev/99-zbt2.rules`:

```bash
sudo install -m 0644 host/dietpi/udev/99-zbt2.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
ls -l /dev/zbt2
```

The rule creates `/dev/zbt2` with group `dialout`. Use it in ZHA and in the Deployment.

### Mount options

Preferred: mount the stable symlink as a character device.

```yaml
volumes:
  - name: zbt2
    hostPath:
      path: /dev/zbt2
      type: CharDevice
```

Fallback: mount the whole by-id directory.

```yaml
volumes:
  - name: serial
    hostPath:
      path: /dev/serial/by-id
      type: Directory
```

If the device is absent at start, Home Assistant still starts and ZHA reports the coordinator as
unavailable. A small wait script may log a clear warning and optionally fail the pod when
`REQUIRE_ZBT2=true`. Do not block all household automation on a missing Zigbee stick by default.

### ZHA reconfiguration after migration

The existing Mac setup uses the RFC2217 bridge
`rfc2217://host.docker.internal:6638`, which does not exist in the cluster. The restore init
container calls `fix-zha-serial.py`, which rewrites every ZHA config entry to:

- path `/dev/zbt2`
- flow control `hardware`
- baud rate `460800`

It keeps a timestamped backup of `.storage/core.config_entries`. On 2026-10-25 the Home Assistant
process held `/dev/zbt2` open and `zigbee.db` was updated after startup.

If the automatic patch is disabled (`ZHA_SERIAL_PATH` unset) or fails, reconfigure through the UI:

1. **Settings → Devices & Services → ZHA → Reconfigure**.
2. Serial device: `/dev/zbt2` (or the by-id path).
3. Radio type: EZSP.
4. Baud rate: `460800`.
5. Flow control: hardware.

If ZHA refuses the change, stop Home Assistant and edit the ZHA entry in
`.storage/core.config_entries` only as a last resort; keep the generated backup.

## First migration from the Mac

1. Stop the Mac deployment so `.storage` and SQLite are consistent:

   ```bash
   docker compose stop home-assistant
   ```

2. Create the state bundle with `scripts/create-state-bundle.sh`. The script defaults to
   `../home-sweet-home/home-sweet-home-home-assistant/config` and writes to `bundles/`.
3. Commit the app with `replicas: 0` so the PVC exists without starting Home Assistant.
4. Upload the bundle with `scripts/upload-state-bundle.sh`. The helper pod triggers `local-path`
   provisioning and copies the archive into `/config/import/`.
5. Set `replicas: 1`, commit, and follow the `seed-config`, `restore-state`, and `configure-http`
   init containers until Home Assistant starts.
6. Verify entities, integrations, dashboards, secrets, ZHA, and backups.
7. Pull a fresh backup back to the Mac and verify its checksum.

The Mac Compose deployment is stopped after migration and should not be started again while the
cluster owns the ZBT-2.

If the volume is empty and no bundle is uploaded, Home Assistant starts with the tracked YAML and
onboarding. That is acceptable only for a new installation.

## Image automation

```yaml
apiVersion: image.toolkit.fluxcd.io/v1
kind: ImageRepository
metadata:
  name: home-assistant
  namespace: flux-system
spec:
  image: ghcr.io/sousa99/home-sweet-home-home-assistant
  interval: 5m
---
apiVersion: image.toolkit.fluxcd.io/v1
kind: ImagePolicy
metadata:
  name: home-assistant
  namespace: flux-system
spec:
  imageRepositoryRef:
    name: home-assistant
  filterTags:
    pattern: '^main-[0-9]{14}-[0-9a-f]{7}$'
  policy:
    alphabetical:
      order: asc
---
apiVersion: image.toolkit.fluxcd.io/v1
kind: ImageUpdateAutomation
metadata:
  name: home-assistant
  namespace: flux-system
spec:
  interval: 5m
  sourceRef:
    kind: GitRepository
    name: flux-system
  git:
    checkout:
      ref:
        branch: main
    commit:
      author:
        name: fluxcdbot
        email: fluxcdbot@users.noreply.github.com
      messageTemplate: 'chore: update home-assistant image'
    push:
      branch: main
  update:
    strategy: Setters
    path: ./apps/home-assistant
```

The Deployment image line carries the setter marker:

```yaml
image: ghcr.io/sousa99/home-sweet-home-home-assistant:main-20261024120000-abcdef0 # {"$imagepolicy": "flux-system:home-assistant"}
```

Bootstrap with `--read-write-key`; otherwise the push fails.

## Verification

```bash
flux get image repository -A
flux get image policy -A
flux get image update -A
kubectl -n home-assistant get pods,pvc,svc,ingressroute
kubectl -n home-assistant logs deploy/home-assistant --tail=100
curl -I http://dietpi/
```

Expected: pod `Running`, PVC `Bound`, service present, ingress route present, and the UI reachable
over the tailnet.

Verified on 2026-10-25:

- `curl -s -o /dev/null -w '%{http_code}' http://dietpi/` returned `200`.
- Deployment `1/1`; PVC `Bound` with 10 GiB.
- `.storage/http` contains `use_x_forwarded_for: true` and the two cluster CIDRs.
- The Home Assistant process holds `/dev/zbt2`; `zigbee.db` was updated at startup.
- Flux image automation selected `main-20261025084504-004e937`.

Inside the pod:

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  sh -c 'ls -la /config | head; test -f /config/.storage/core.config_entries && echo storage-ok'
```

## Rollback and upgrades

- **Configuration rollback:** revert the commit in the configuration repository. A new image is
  published and Flux updates the Deployment.
- **Image rollback:** commit the previous image tag in `apps/home-assistant/deployment.yaml` and
  reconcile. Do not use `kubectl set image` as the permanent fix.
- **Home Assistant upgrade:** the base image tracks `stable`. Pin a digest or version tag if
  upgrades need to be deliberate. Read release notes and back up before a major version.
- **Failed restore:** the init container must not leave a half-applied archive marked as applied.
  Keep the previous bundle and a backup on the volume.

## Security notes

- `privileged: true` is required for v1 to access the serial device; it is not required for Home
  Assistant itself. Revisit when the device access can be narrowed.
- The image is public and contains only tracked configuration.
- `.storage` contains integration credentials; it lives on the PVC.
- `secrets.yaml`, if used, is created manually and never committed. See
  [07-secrets-and-unsynced-state.md](07-secrets-and-unsynced-state.md).
