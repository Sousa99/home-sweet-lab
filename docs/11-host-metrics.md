# 11 — Host metrics exporter and Home Assistant sensors

> **Legacy Home Assistant path.** The primary Home Assistant integration is now MQTT discovery,
> which creates one `home-sweet-lab-server` device. See [`12-host-metrics-mqtt.md`](12-host-metrics-mqtt.md).
> This document remains the HTTP exporter and legacy Scrape reference. The HTTP endpoints still work.

This document owns the operator contract for the DietPi host-metrics exporter: how it is exposed,
the exact metric names and units, the legacy Home Assistant Scrape UI steps, verification, and
recovery. The exporter manifests are in [`../apps/host-metrics/`](../apps/host-metrics/). The design
contract is in
[`../specs/002-host-metrics-exporter/contracts/exporter-api.md`](../specs/002-host-metrics-exporter/contracts/exporter-api.md).

## What it provides

A single-replica, stateless exporter in the `monitoring` namespace, scheduled on `dietpi`, reads
the host through read-only mounts and exposes:

| Measurement | Source | Home Assistant sensor |
| ----------- | ------ | --------------------- |
| CPU/system temperature | hwmon, falling back to thermal zones | `sensor.dietpi_cpu_temperature` (name chosen in the UI) |
| RAM usage | `/proc/meminfo` | `sensor.dietpi_ram_usage` |
| Root filesystem usage | `statvfs("/")` | `sensor.dietpi_storage_usage` |
| Battery charging status | `/sys/class/power_supply/*/status` | `sensor.dietpi_battery_status` |
| Tailscale IPv4 | host network namespace | `sensor.dietpi_tailscale_ipv4` |
| All active IPv4 addresses (optional) | host network namespace | `sensor.dietpi_ipv4_addresses` |

The exporter is a convenience for household visibility, not an availability-critical service. It
does not replace Home Assistant's own recorder, and it is not a monitoring stack.

## Exposure

The exporter is reachable only inside the cluster:

```text
http://host-metrics.monitoring.svc.cluster.local:9100/metrics
http://host-metrics.monitoring.svc.cluster.local:9100/ha
http://host-metrics.monitoring.svc.cluster.local:9100/healthz
http://host-metrics.monitoring.svc.cluster.local:9100/readyz
```

There is no Ingress, Tailscale ingress, LoadBalancer, NodePort, hostPort, hostNetwork, or host PID
namespace. The Service is `ClusterIP`. The cluster has no working NetworkPolicy layer, so any pod
can reach the Service; it is not reachable from outside the cluster.

## Metric contract

`/metrics` is Prometheus text. `/ha` is the flat JSON projection used by the Home Assistant Scrape
UI. The exact names below are the public contract; changing one requires updating this document and
the UI sensors together.

### Temperature

| Metric | Labels | Unit | Notes |
| ------ | ------ | ---- | ----- |
| `host_system_temperature_celsius` | `source`, `chip`, `sensor`, `path` | °C | One series per usable hwmon or thermal-zone reading. |
| `host_metrics_temperature_available` | none | 0 or 1 | `0` when no usable sensor exists. |

`source` is `hwmon` or `thermal_zone`. `chip` is the hwmon name (or `thermal`). `sensor` is the
hwmon label or input file name (or the thermal-zone type). The preferred reading is exposed as the
flat `/ha` value; usually this is a CPU package sensor such as `coretemp` or `k10temp`.

### Memory

| Metric | Unit | Notes |
| ------ | ---- | ----- |
| `host_memory_total_bytes` | bytes | Total usable memory. |
| `host_memory_available_bytes` | bytes | `MemAvailable`, with a fallback when the kernel omits it. |
| `host_memory_used_bytes` | bytes | `total - available`. |
| `host_memory_usage_percent` | percent | `used / total * 100`, one decimal. |

### Root filesystem

All filesystem series carry `mountpoint="/"`.

| Metric | Unit | Notes |
| ------ | ---- | ----- |
| `host_filesystem_size_bytes` | bytes | Total capacity. |
| `host_filesystem_available_bytes` | bytes | Available to an unprivileged process (`f_bavail`). |
| `host_filesystem_used_bytes` | bytes | `size - available`; reserved blocks count as used. |
| `host_filesystem_usage_percent` | percent | `used / size * 100`, one decimal. |

### IPv4 addresses

| Metric | Labels | Unit | Notes |
| ------ | ------ | ---- | ----- |
| `host_network_ipv4_info` | `interface`, `address`, `tailscale` | 1 (info metric) | Every active non-loopback IPv4 address. |

`tailscale` is `"true"` only for `interface="tailscale0"`. Use the Tailscale sensor for the stable
address; use the optional all-IPv4 sensor to see LAN and virtual interfaces.

### Battery status

| Metric | Labels | Unit | Notes |
| ------ | ------ | ---- | ----- |
| `host_battery_status_info` | `device`, `status`, `path` | 1 (info metric) | One series per readable battery. |
| `host_metrics_battery_available` | none | 0 or 1 | `0` when no readable battery exists. |

`status` is the raw kernel string: `Charging`, `Discharging`, `Full`, `Not charging`, or `Unknown`.
The exporter does not map `Full` or `Not charging` to a binary charging/discharging value. If
multiple batteries exist, all are exposed; the lexicographically first device (for example `BAT0`)
is the preferred battery used by the single Home Assistant sensor.

### Exporter identity

`host_metrics_info{version="1"} 1` is always present.

### Absence behavior

- No temperature sensor: temperature series omitted, `host_metrics_temperature_available 0`, and
  `temperature_c` is `null`.
- No battery: battery series omitted, `host_metrics_battery_available 0`, and `battery_status` is
  `null`.
- Memory or root filesystem unreadable: those families are omitted, `/readyz` returns `503`, and
  the pod does not become Ready.
- Host network source unreadable: IPv4 series omitted; memory, storage, temperature, and battery
  continue, and `/readyz` remains `200`.
- Exporter down: Home Assistant sensors become unavailable at the next poll.

## `/ha` JSON keys

The Home Assistant UI uses `select: body` and `value_json`. The complete key list is:

```text
collected_at
temperature_c
temperature_source
temperature_path
memory_total_bytes
memory_available_bytes
memory_used_bytes
memory_usage_percent
storage_total_bytes
storage_available_bytes
storage_used_bytes
storage_usage_percent
ipv4_addresses[]   (interface, address, tailscale, netmask?)
tailscale_ipv4
battery_status
battery_device
battery_path
battery_statuses[] (device, status, path, preferred)
```

## Legacy Home Assistant Scrape UI steps

Use MQTT instead unless you are intentionally validating the legacy path. See
[`12-host-metrics-mqtt.md`](12-host-metrics-mqtt.md).

Do this manually in the Home Assistant UI. Do not add YAML, HACS, automations, or a Home Assistant
configuration-repository change.

1. Open **Settings > Devices & services > Add Integration**.
2. Select **Scrape**.
3. Use the resource URL `http://host-metrics.monitoring.svc.cluster.local:9100/ha`, method `GET`,
   no authentication, timeout `10`, encoding `UTF-8`.
4. Submit and create one sensor subentry per row below. Use **Add entry** (or **Add sensor**) for
   each additional sensor.
5. The `select` value is always `body`.

| Sensor | Value template | Availability template | Unit | Device class | State class |
| ------ | -------------- | --------------------- | ---- | ------------ | ----------- |
| DietPi CPU temperature | `{{ value_json.temperature_c }}` | `{{ value_json.temperature_c is not none }}` | °C | Temperature | Measurement |
| DietPi RAM usage | `{{ value_json.memory_usage_percent }}` | `{{ value_json.memory_usage_percent is not none }}` | % | none | Measurement |
| DietPi storage usage | `{{ value_json.storage_usage_percent }}` | `{{ value_json.storage_usage_percent is not none }}` | % | none | Measurement |
| DietPi battery status | `{{ value_json.battery_status }}` | `{{ value_json.battery_status is not none }}` | none | none | none |
| DietPi Tailscale IPv4 | `{{ value_json.tailscale_ipv4 }}` | `{{ value_json.tailscale_ipv4 is not none }}` | none | none | none |
| DietPi IPv4 addresses (optional) | `{{ value_json.ipv4_addresses \| map(attribute='address') \| join(', ') }}` | `{{ value_json.ipv4_addresses \| length > 0 }}` | none | none | none |

The Scrape UI does not expose a scan interval. Home Assistant polls every **10 minutes**. To force
an immediate refresh after adding or editing a sensor, open the Scrape integration's three-dot menu
and choose **Reload**.

### Manual handoff checklist

Record the entity IDs and first observed states here after performing the UI steps. Do not commit
runtime IP addresses or other household data; use the entity ID and a general state description.

| Sensor | Entity ID | First observed state | Notes |
| ------ | --------- | -------------------- | ----- |
| Temperature |  |  |  |
| RAM usage |  |  |  |
| Storage usage |  |  |  |
| Battery status |  |  |  |
| Tailscale IPv4 |  |  |  |
| All IPv4 (optional) |  |  |  |

## Verification

Run these from the repository root. The endpoint checks use the Home Assistant pod's Python.

```bash
flux get kustomizations apps
kubectl -n monitoring get namespace,configmap,deployment,service,pod -o wide
kubectl -n monitoring rollout status deployment/host-metrics --timeout=120s
```

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://host-metrics.monitoring.svc.cluster.local:9100/metrics', timeout=5).read().decode())"
```

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://host-metrics.monitoring.svc.cluster.local:9100/ha', timeout=5).read().decode())"
```

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://host-metrics.monitoring.svc.cluster.local:9100/readyz', timeout=5).status)"
```

Expected:

- The `apps` Kustomization is Ready.
- The `monitoring` namespace exists, the ConfigMap has a hash suffix, the Deployment has one
  available replica, and the pod is Ready on `dietpi`.
- `/metrics` returns HTTP 200 with the available families.
- `/ha` returns the documented keys, with `battery_status` null if the host has no battery.
- `/readyz` returns `200` when memory and root filesystem collection succeed.

### Exposure check

```bash
kubectl -n monitoring get service host-metrics -o jsonpath='{.spec.type}{"\n"}'
kubectl -n monitoring get deployment host-metrics \
  -o jsonpath='{.spec.template.spec.hostNetwork}{"\n"}{.spec.template.spec.hostPID}{"\n"}'
kubectl -n monitoring get deployment host-metrics \
  -o jsonpath='{.spec.template.spec.containers[0].securityContext.privileged}{"\n"}'
kubectl get ingress -A | grep -i host-metrics || echo "no host-metrics ingress"
```

Expected: `ClusterIP`; empty or `false` for `hostNetwork`, `hostPID`, and `privileged`; no Ingress.
Do not expose the exporter through Traefik, Tailscale, a NodePort, a LoadBalancer, or a host port.

### Battery status check

```bash
ls /sys/class/power_supply
cat /sys/class/power_supply/<device>/type
cat /sys/class/power_supply/<device>/status
```

Run those on the host. A `Battery` device with a readable `status` produces
`host_battery_status_info` and a non-null `battery_status`. If there is no battery, the expected
state is an absent battery family with `host_metrics_battery_available 0`; the Home Assistant
battery sensor is unavailable by design.

## Recovery and failure behavior

### Exporter down

All Home Assistant sensors become unavailable at the next poll. Nothing is fabricated. Check the
Deployment and logs:

```bash
kubectl -n monitoring get deployment,pod -o wide
kubectl -n monitoring logs deployment/host-metrics
kubectl -n monitoring get events --sort-by=.lastTimestamp | tail -30
```

If the pod is `Pending`, check the `dietpi` node selector and the control-plane toleration. If it is
`ContainerCreating`, check the hostPath events. If it is `CrashLoopBackOff`, check the logs for a
missing/unreadable host path.

### Pod restart

Delete the pod and let the Deployment replace it:

```bash
kubectl -n monitoring delete pod -l app.kubernetes.io/name=host-metrics
kubectl -n monitoring rollout status deployment/host-metrics --timeout=120s
```

The endpoint should return within 2 minutes. Home Assistant sensors recover at the next 10-minute
poll or after **Reload**; no sensor reconfiguration is needed.

### Node reboot

Reboot `dietpi` through the host procedure in [`01-hardware-and-dietpi.md`](01-hardware-and-dietpi.md)
and [`02-k3s.md`](02-k3s.md). After the node returns:

```bash
kubectl get nodes
flux get kustomizations apps
kubectl -n monitoring get pod -o wide
kubectl -n monitoring rollout status deployment/host-metrics --timeout=180s
```

Expected: the node is Ready, Flux reconciles the workload, the pod is Ready on `dietpi`, and the
endpoint reports current IPv4 and battery values. Home Assistant recovers without reconfiguration.

### No temperature sensor

The exporter remains Ready. `/metrics` omits `host_system_temperature_celsius` and reports
`host_metrics_temperature_available 0`; `/ha` reports `temperature_c: null`; the Home Assistant
temperature sensor becomes unavailable. Do not replace the value with zero.

### No battery or unreadable battery status

The exporter remains Ready. `/metrics` omits `host_battery_status_info` and reports
`host_metrics_battery_available 0`; `/ha` reports `battery_status: null` and an empty
`battery_statuses`; the Home Assistant battery status sensor becomes unavailable. A battery that is
removed at runtime disappears on the next scrape. Do not add NUT/UPS, USB access, or a privileged
helper just to make the sensor available.

### HostPath permissions or missing paths

- A missing hostPath prevents the pod from starting; the event names the path.
- An unreadable `/host/proc/meminfo` or `/host/root` makes `/readyz` return `503` and the pod does
  not become Ready.
- An unreadable hwmon input only removes that temperature reading.
- An unreadable `/host/proc/1/net` only removes the IPv4 family.
- An unreadable `power_supply/*/status` only removes that battery reading.

Do not fix permissions by making the container privileged or running it as root. Fix the host path
or document the limitation first.

### Multiple or changing IPv4 addresses

`/ha` lists every active non-loopback address with its interface. The Tailscale sensor uses only
`tailscale0`; if that interface is down, the sensor is unavailable and recovers when it returns.
The optional all-IPv4 sensor changes as interfaces appear or disappear.

### Flux reverts manual changes

Do not edit the running Deployment, Service, or ConfigMap with `kubectl`. Flux reconciles the
tracked `apps` path and reverts manual drift at the next interval. Use Git for changes.

## Verification record

Observed on the `dietpi` cluster on 2026-10-25. A temporary pre-merge apply was used first, then
removed; Flux subsequently reconciled the committed manifests at `main@388a432`. Real IP addresses
are omitted.

| Check | Observed |
| ----- | -------- |
| Flux reconciliation | The `apps` Kustomization is Ready at `main@388a432`; the exporter Deployment is Ready on `dietpi`. |
| Pod readiness | `host-metrics` became Ready on `dietpi`; `/readyz` returned `200` from the `home-assistant` namespace. |
| Service DNS | `http://host-metrics.monitoring.svc.cluster.local:9100/metrics` returned HTTP 200 from the Home Assistant pod. |
| Temperature | hwmon sources were present; the preferred reading was `coretemp` / `Package id 0`. |
| Memory and storage | All memory and root-filesystem families were present; `mountpoint="/"` was correct. |
| IPv4 | The Tailscale address mapped to `interface="tailscale0"` with `tailscale="true"`; LAN and `cni0` addresses were also listed. |
| Battery | One `BAT0` battery was present with raw status `Full`; `host_metrics_battery_available` was `1`. |
| Exposure | Service type `ClusterIP`; no Ingress, `hostNetwork`, `hostPID`, `hostPort`, or privileged mode. |
| Pod restart | Deleting the pod produced a replacement that became Ready; `/readyz` returned `200` again. |
| Flux drift | Scaling the Deployment to zero was reverted to one replica by Flux reconciliation. |
| Absent sources | Unit tests cover no temperature, no battery, unreadable battery status, missing memory, and missing root filesystem; the live host had both temperature and battery. |

Still pending: the manual Home Assistant UI sensor creation and the node-reboot drill. Flux
reconciliation, pod replacement, and Flux drift correction are verified.

## Security and trade-offs

- No secrets, tokens, kubeconfigs, or real tailnet identifiers are used or exposed.
- The pod runs as non-root UID/GID 65534, drops all capabilities, disallows privilege escalation,
  uses a read-only root filesystem, and mounts no writable host path.
- `/proc/meminfo`, `/proc/1/net`, `/sys`, and `/` are mounted read-only. The host `/` mount is the
  broadest exposure; it exists only for `statvfs("/")`, and the script never writes to it.
- `/proc/1/net` is a narrow read of the host network namespace; host networking and host PID sharing
  are not used.
- The runtime image is the official `python:3.12-alpine` image pinned by digest. Docker Hub is the
  only new image dependency; if it is unavailable and the image is not cached, the exporter cannot
  start. The other workloads are unaffected.
- The cluster has no reliable NetworkPolicy layer, so the ClusterIP Service is reachable by any pod
  in the cluster. It is not reachable from outside the cluster.

## Limitations and non-goals

- The Home Assistant Scrape UI has no scan-interval field; polling is every 10 minutes. Faster
  polling requires YAML or HACS, which are out of scope.
- No battery percentage, health, runtime, or UPS/NUT integration.
- No Prometheus, Grafana, alerting, recording rules, or long-term metric storage.
- No per-container, per-pod, or per-application metrics.
- No IPv6 address reporting.
- No external access to the exporter.
- No Home Assistant YAML, HACS, automations, scenes, dashboards, or changes to the Home Assistant
  configuration repository.
- A host without a battery or temperature sensor is supported by making those sensors unavailable;
  the feature does not invent data.

## Related documents

- [`../specs/002-host-metrics-exporter/contracts/exporter-api.md`](../specs/002-host-metrics-exporter/contracts/exporter-api.md) — exact HTTP and metric contract
- [`../specs/002-host-metrics-exporter/contracts/home-assistant-ui.md`](../specs/002-host-metrics-exporter/contracts/home-assistant-ui.md) — exact UI field tables
- [`../specs/002-host-metrics-exporter/quickstart.md`](../specs/002-host-metrics-exporter/quickstart.md) — verification scenarios
- [`09-limitations.md`](09-limitations.md) — cluster-wide limitations
