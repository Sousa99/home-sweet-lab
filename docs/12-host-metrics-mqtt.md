# 12 — MQTT host metrics device

This document owns the MQTT path for the DietPi host metrics. It creates **one Home Assistant
device** named `home-sweet-lab-server` with six entities, replacing the legacy Scrape integration.

- **home-sweet-lab-server** is the Home Assistant device name.
- **DietPi** is the operating system.
- **`dietpi`** is the hostname and Linux user.
- The Kubernetes node remains **`dietpi`**.

The existing HTTP exporter remains available for debugging at
`http://host-metrics.monitoring.svc.cluster.local:9100/`.

## Architecture

```text
DietPi host
  └── host-metrics exporter (monitoring)
        ├── HTTP :9100 (debugging, ClusterIP only)
        └── MQTT publish ──▶ mosquitto.monitoring.svc.cluster.local:1883
                                  │
                                  ▼
                         Home Assistant MQTT integration
                                  │
                                  ▼
                         One device: home-sweet-lab-server
```

The broker is a ClusterIP-only Mosquitto Deployment in `monitoring`. It is not exposed through
Traefik, Tailscale, a LoadBalancer, a NodePort, or a host port.

## Prerequisites

- The `host-metrics` app has been reconciled at least once so the `monitoring` namespace exists.
- `kubectl` points at the `dietpi` cluster.
- Docker and OpenSSL are available on the machine where you run the Secret script.
- You can sign in to Home Assistant as an administrator.

## Verification status (2026-10-25)

- The custom exporter image was built locally and the paho-gated tests pass.
- A local Mosquitto broker with the two-user ACL was tested with the exporter image:
  discovery, state, availability, authentication, ACL denial, and Last Will offline were observed.
- The broker manifests were applied temporarily to `monitoring`: the broker became Ready, the
  `exporter` user could publish, the `homeassistant` user could read and write only its allowed
  topics, and a denied write did not change retained state. The temporary broker and Secret were
  removed after the check.
- Still pending: the first GHCR image publication, Flux reconciliation of the committed MQTT
  manifests, the Home Assistant MQTT integration, removal of legacy Scrape sensors, and the node
  reboot drill.

Real IP addresses are omitted from this document.

## 1. Create the MQTT Secret

The broker and exporter use two MQTT users, `exporter` and `homeassistant`. The credentials are a
manual Kubernetes Secret, never committed.

From the repository root:

```bash
./scripts/create-mqtt-secret.sh
```

The script:

- generates random passwords;
- builds a Mosquitto password file with both users;
- creates `secret/monitoring/mosquitto-auth` with `passwd`, exporter credentials, and Home
  Assistant credentials;
- prints the Home Assistant username/password.

Store the Home Assistant password in your password manager. You will enter it in the MQTT
integration UI. The exporter password stays in the Secret and is injected into the exporter pod.

If the Secret already exists, use `--rotate` intentionally:

```bash
./scripts/create-mqtt-secret.sh --rotate
kubectl -n monitoring rollout restart deployment/mosquitto deployment/host-metrics
```

After rotation, update the Home Assistant MQTT integration password in the UI.

Do not commit the password file, the Secret YAML, or the printed password.

## 2. Deploy

The broker and exporter are reconciled by Flux from `main`. The exporter image is published by the
`Publish host-metrics image` GitHub Actions workflow when the exporter code changes.

```bash
flux reconcile kustomization apps --with-source
flux get kustomizations apps
kubectl -n monitoring get configmap,deployment,service,pod -o wide
kubectl -n monitoring rollout status deployment/mosquitto --timeout=120s
kubectl -n monitoring rollout status deployment/host-metrics --timeout=120s
```

Expected:

- a `mosquitto` Deployment and ClusterIP Service on 1883;
- a `mosquitto-config` ConfigMap;
- a `host-metrics` Deployment using the custom GHCR image;
- the exporter pod Ready on `dietpi`;
- no Ingress, hostPort, hostNetwork, hostPID, or privileged mode.

If the exporter is in `ImagePullBackOff`, the first image may not have been published yet. Wait for
the GitHub Actions workflow and the Flux image automation, then reconcile again. The GHCR package
must be public, or the pod needs an image pull Secret.

First-rollout note: the exporter image is built by GitHub Actions. If the Deployment is reconciled
before the image exists, it stays in `ImagePullBackOff` and the previous HTTP exporter may be
replaced. To avoid a gap, push the exporter code first, wait for the workflow to publish the image,
then reconcile the Deployment. Subsequent code updates use the same image automation path.

## 3. Verify the broker and topics

Check readiness and logs:

```bash
kubectl -n monitoring get pod -o wide
kubectl -n monitoring logs deployment/mosquitto
kubectl -n monitoring logs deployment/host-metrics
```

Inspect retained discovery and state with the Home Assistant MQTT user. Replace `<password>` with
the password printed by the Secret script.

```bash
kubectl -n monitoring exec deploy/mosquitto -- \
  mosquitto_sub -h localhost -u homeassistant -P '<password>' \
  -t 'homeassistant/sensor/#' -C 6 -W 10 -v
```

```bash
kubectl -n monitoring exec deploy/mosquitto -- \
  mosquitto_sub -h localhost -u homeassistant -P '<password>' \
  -t 'home-sweet-lab-server/state' -C 1 -W 10 -v
```

Expected:

- six retained discovery messages;
- every discovery payload has `device.identifiers = ["home-sweet-lab-server"]`;
- a retained state message with `temperature_c`, `memory_usage_percent`,
  `storage_usage_percent`, `battery_status`, `tailscale_ipv4`, and `ipv4_addresses`;
- availability topics `online`.

The exact topics and entity IDs are in
[`../specs/003-host-metrics-mqtt-device/contracts/mqtt-discovery.md`](../specs/003-host-metrics-mqtt-device/contracts/mqtt-discovery.md).

## 4. Add the Home Assistant MQTT integration

Do this in the Home Assistant UI.

1. Open **Settings > Devices & services**.
2. Select **Add Integration**.
3. Search for **MQTT** and select it.
4. Choose **Manually enter the MQTT broker connection details**.
5. Enter:
   - **Broker**: `mosquitto.monitoring.svc.cluster.local`
   - **Port**: `1883`
   - **MQTT protocol**: leave the default
   - **Username**: `homeassistant`
   - **Password**: the password printed by the Secret script
6. Leave TLS and other settings at their defaults. The broker is cluster-internal and plain MQTT.
7. Submit.

Home Assistant connects, receives the retained discovery messages, and creates the
`home-sweet-lab-server` device.

## 5. Verify the device

1. Open **Settings > Devices & services > MQTT**.
2. Open **Devices** and select `home-sweet-lab-server`.
3. Confirm these entities:

| Entity ID | Expected |
| --------- | -------- |
| `sensor.home_sweet_lab_server_cpu_temperature` | Numeric CPU package temperature |
| `sensor.home_sweet_lab_server_ram_usage` | RAM percentage, 0–100 |
| `sensor.home_sweet_lab_server_storage_usage` | Root filesystem percentage, 0–100 |
| `sensor.home_sweet_lab_server_battery_status` | Raw state such as `Charging`, `Discharging`, `Full`, `Not charging`, or `Unknown` |
| `sensor.home_sweet_lab_server_tailscale_ipv4` | Dotted-quad Tailscale address |
| `sensor.home_sweet_lab_server_ipv4_addresses` | Comma-separated active IPv4 addresses |

Values update every 30 seconds by default. If they do not update, check the exporter logs and the
MQTT integration logs.

The current host reports `BAT0` as `Full`, so the battery entity should show `Full` until the
battery starts charging or discharging.

## 6. Remove the legacy Scrape integration

Do this only after the MQTT device and all six entities are verified.

1. Open **Settings > Devices & services**.
2. Find the **Scrape** integration used for the old DietPi sensors.
3. Remove the integration.
4. Delete any orphaned Scrape devices or entities.
5. Confirm the `home-sweet-lab-server` MQTT entities remain and update.

Do not create new Scrape sensors. MQTT is the primary path; HTTP is for debugging.

## Recovery

### Exporter down or restart

The broker publishes the Last Will `offline` on `home-sweet-lab-server/availability`, and all MQTT
entities become unavailable. When the exporter returns, it publishes `online`, discovery, and
state. Check:

```bash
kubectl -n monitoring get deployment,pod -o wide
kubectl -n monitoring logs deployment/host-metrics
kubectl -n monitoring rollout status deployment/host-metrics --timeout=120s
```

### Broker down or restart

The exporter reconnects and republishes discovery, availability, and state. The broker has no PVC,
so retained messages are lost on restart and recreated by the exporter. Check:

```bash
kubectl -n monitoring get deployment,pod -o wide
kubectl -n monitoring logs deployment/mosquitto
kubectl -n monitoring rollout status deployment/mosquitto --timeout=120s
```

### Home Assistant restart

Home Assistant publishes `homeassistant/status=online`. The exporter subscribes and republishes
discovery, availability, and state. If entities do not return, publish a test birth message:

```bash
kubectl -n monitoring exec deploy/mosquitto -- \
  mosquitto_pub -h localhost -u homeassistant -P '<password>' \
  -t homeassistant/status -m online
```

### Node reboot

After the node returns:

```bash
kubectl get nodes
flux get kustomizations apps
kubectl -n monitoring get pod -o wide
kubectl -n monitoring rollout status deployment/mosquitto --timeout=180s
kubectl -n monitoring rollout status deployment/host-metrics --timeout=180s
```

Home Assistant recovers without recreating the device or entities.

### Missing temperature, battery, or IPv4

Only the affected per-source availability topic goes `offline`; the other entities stay available.
The state payload uses `null`/empty values for the missing source. Do not replace missing data with
zero.

### Authentication or ACL failure

Symptoms include repeated MQTT connection failures, HA MQTT integration errors, or missing topics.
Check:

```bash
kubectl -n monitoring logs deployment/mosquitto
kubectl -n monitoring logs deployment/host-metrics
kubectl -n monitoring get secret mosquitto-auth
```

Verify the ACL in `apps/host-metrics/mqtt/configmap.yaml` and the Secret keys. If credentials were
rotated, restart both deployments and update the HA MQTT integration password.

### Image pull failure

If the exporter pod is in `ImagePullBackOff`:

1. Check the GitHub Actions workflow result.
2. Confirm the GHCR package is public, or add an image pull Secret.
3. Check `ImageRepository`/`ImagePolicy`/`ImageUpdateAutomation` status.
4. Reconcile Flux after the image exists.

## Security and tradeoffs

- Mosquitto and the exporter are ClusterIP-only; no external MQTT.
- Two users with ACLs: exporter writes only its topics; HA reads them and writes its birth topic.
- The MQTT Secret is manual and never committed. The HA MQTT integration stores its copy in HA
  `.storage`.
- No TLS inside the cluster in v1. Auth and ACLs are the boundary; TLS is a future change.
- The broker is ephemeral; retained discovery/state is republished after broker restarts.
- The exporter runs as UID/GID 65534; the broker as UID/GID 1883. Both drop all capabilities, use a
  read-only root filesystem, and avoid host networking/PID/ports.
- The custom exporter image is published to GHCR with immutable tags. The broker uses the pinned
  `eclipse-mosquitto:2` digest.
- No Home Assistant YAML, HACS, automations, or Home Assistant repository changes.

## Limitations

- No MQTT TLS or external MQTT access.
- No broker persistence/PVC; retained messages are ephemeral.
- No battery percentage, health, runtime, or NUT/UPS integration.
- No Prometheus, Grafana, alerting, or long-term metric storage.
- No per-container, per-pod, or application metrics.
- No IPv6 address reporting.
- The first publish depends on the GitHub Actions image workflow and GHCR package visibility.
- The Kubernetes node, hostname, Linux user, and OS remain `dietpi`; only the HA device identity is
  `home-sweet-lab-server`.

## Related documents

- [`../specs/003-host-metrics-mqtt-device/contracts/mqtt-discovery.md`](../specs/003-host-metrics-mqtt-device/contracts/mqtt-discovery.md) — topics, entities, ACLs
- [`../specs/003-host-metrics-mqtt-device/spec.md`](../specs/003-host-metrics-mqtt-device/spec.md) — requirements
- [`11-host-metrics.md`](11-host-metrics.md) — HTTP exporter and legacy Scrape path
- [`09-limitations.md`](09-limitations.md) — cluster-wide limitations
