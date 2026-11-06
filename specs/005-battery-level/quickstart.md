# Quickstart: Battery Level Percentage

**Feature**: `specs/005-battery-level`
**Purpose**: Validate the battery-level addition locally and on the real `dietpi` cluster.
**Contracts**: [battery-level-additions.md](./contracts/battery-level-additions.md)
**Data model**: [data-model.md](./data-model.md)

This guide contains commands and expected outcomes, not implementation code.

## Prerequisites

- `kubectl` points at the `dietpi` cluster and the node is Ready.
- The Flux `apps` Kustomization is reconciling `main`.
- The `host-metrics` exporter, `mosquitto` broker, and Home Assistant MQTT integration are already
  working from the previous host-metrics features.
- The MQTT Secret `mosquitto-auth` exists in `monitoring`.
- You have the Home Assistant MQTT password available outside Git.
- Local validation tools: `python3`, `kubectl`; `kubeconform` and `yamllint` when installed.

## 1. Validate locally before merging

```bash
python -m unittest discover -s apps/host-metrics -p 'test_*.py'
kubectl kustomize apps/host-metrics
kubeconform -strict -summary apps/host-metrics
```

Expected:

- Unit tests pass, including collection with level present/absent, metrics, flat JSON, discovery,
  and state.
- Kustomize renders without errors and includes the updated ACL ConfigMap.
- kubeconform reports no invalid resources.

If `./scripts/validate.sh` exists, run it instead and do not treat a skipped tool as a pass.

## 2. Merge and reconcile

Merge the exporter code, ACL, tests, and docs. Then:

```bash
flux reconcile kustomization apps --with-source
flux get kustomizations apps
kubectl -n monitoring get configmap,deployment,pod -o wide
kubectl -n monitoring rollout status deployment/host-metrics --timeout=180s
kubectl -n monitoring rollout status deployment/mosquitto --timeout=180s
```

Expected:

- `apps` is `Ready: True`.
- The exporter and broker roll out; the exporter becomes Ready on `dietpi`.
- The new image tag is recorded in the Deployment by Flux image automation.

If the exporter is in `ImagePullBackOff`, wait for the `Publish host-metrics image` workflow and
then reconcile again.

## 3. Verify the HTTP exporter

Read `/metrics` and `/ha` from the Home Assistant namespace:

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://host-metrics.monitoring.svc.cluster.local:9100/metrics', timeout=5).read().decode())"
```

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://host-metrics.monitoring.svc.cluster.local:9100/ha', timeout=5).read().decode())"
```

Expected on a host with a readable level:

- A `host_battery_level_percent{device="BAT0",path="/host/sys/class/power_supply/BAT0/capacity"}`
  sample with a value from `0` to `100`.
- The existing `host_battery_status_info` sample is still present.
- `/ha` contains `battery_level_percent` as an integer and each `battery_statuses[]` entry contains
  `level_percent`.
- `/readyz` still returns `200`.

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://host-metrics.monitoring.svc.cluster.local:9100/readyz', timeout=5).status)"
```

## 4. Verify the MQTT discovery and state

Use the Home Assistant MQTT user. Replace `<password>` from the Secret. Do not paste credentials
into Git or a shared terminal log.

```bash
kubectl -n monitoring exec deploy/mosquitto -- \
  mosquitto_sub -h localhost -u homeassistant -P '<password>' \
  -t 'homeassistant/sensor/#' -C 7 -W 10 -v
```

Expected: seven retained discovery messages, including
`homeassistant/sensor/home_sweet_lab_server_battery_level/config`. Its payload has unit `%`,
device class `battery`, state class `measurement`, and battery-source availability.

```bash
kubectl -n monitoring exec deploy/mosquitto -- \
  mosquitto_sub -h localhost -u homeassistant -P '<password>' \
  -t 'home-sweet-lab-server/state' -C 1 -W 10 -v
```

Expected: the state JSON includes `battery_level_percent` and per-battery `level_percent` alongside
the existing battery status keys.

If the discovery message is missing, check the broker ACL and the exporter logs:

```bash
kubectl -n monitoring logs deployment/mosquitto
kubectl -n monitoring logs deployment/host-metrics
```

## 5. Verify in Home Assistant

1. Open **Settings > Devices & services > MQTT > Devices**.
2. Select `home-sweet-lab-server`.
3. Confirm the entity `sensor.home_sweet_lab_server_battery_level` exists.
4. Confirm it shows a percentage matching the host and updates within 60 seconds.
5. Confirm the existing `sensor.home_sweet_lab_server_battery_status` still shows the charging
   state.

No manual entity creation and no Home Assistant configuration change are required.

## 6. Verify absence and recovery

### Status-only battery

On a test fixture or an edited local unit-test fixture, provide `status` without `capacity`.

Expected: the battery status entity still works, no level metric is emitted for that device, the
level entity has no valid value, and `/readyz` remains `200`.

### No battery

Against a fixture with no `power_supply` battery.

Expected: `host_metrics_battery_available 0`, no battery metric families, `battery_status` and
`battery_level_percent` null in `/ha`, and both battery entities unavailable.

### Exporter restart

```bash
kubectl -n monitoring delete pod -l app.kubernetes.io/name=host-metrics
kubectl -n monitoring rollout status deployment/host-metrics --timeout=180s
```

Expected: entities become unavailable through the Last Will, then return after the replacement
publishes discovery and state. The battery level matches the host again without reconfiguration.

### Broker restart

```bash
kubectl -n monitoring delete pod -l app.kubernetes.io/name=mosquitto
kubectl -n monitoring rollout status deployment/mosquitto --timeout=180s
```

Expected: the exporter reconnects and republishes all seven discovery messages, state, and
availability.

## 7. Rollback

Revert the feature commit and reconcile:

```bash
flux reconcile kustomization apps --with-source
kubectl -n monitoring rollout status deployment/host-metrics --timeout=180s
```

The old six-entity device continues to work. The battery-level entity becomes stale/unavailable;
delete it in the Home Assistant MQTT device if it does not disappear automatically after the
retained discovery topic is cleared or replaced.
