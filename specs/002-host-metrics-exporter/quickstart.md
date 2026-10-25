# Quickstart: Host Metrics Exporter and Home Assistant Integration

**Feature**: `specs/002-host-metrics-exporter`
**Purpose**: Run and verify the feature end to end on the real `dietpi` cluster.
**Contracts**: [exporter-api.md](./contracts/exporter-api.md) and
[home-assistant-ui.md](./contracts/home-assistant-ui.md)

This guide does not contain the exporter implementation. It describes the commands and expected
outcomes that prove the implementation meets the specification.

## Prerequisites

- `kubectl` points at the `dietpi` cluster and the node is Ready.
- The Flux `apps` Kustomization is reconciling `main`.
- The `home-assistant` namespace has a running Home Assistant pod.
- The Home Assistant UI is reachable at `https://home-assistant.<tailnet>.ts.net/`.
- You have cluster-admin access to delete a pod and to create a one-off debug pod.
- `scripts/validate.sh` dependencies are installed locally (`kubectl` and, preferably,
  `kubeconform`, `yamllint`, `gitleaks`, `python3`).

## P1 — Deploy and verify the exporter

### 1. Validate locally before merging

```bash
./scripts/validate.sh
```

Expected: Kustomize renders `apps/` and `infrastructure/`, kubeconform reports no errors, yamllint
passes, gitleaks finds no secrets, and the exporter unit tests pass.

If a tool is missing, the script skips it and prints a warning. Do not treat a skipped schema or
secret check as a pass.

### 2. Merge and reconcile

Merge the `apps/host-metrics` manifests and the `apps/kustomization.yaml` update. Then:

```bash
flux reconcile kustomization apps --with-source
flux get kustomizations apps
kubectl -n monitoring get namespace,configmap,deployment,service,pod -o wide
kubectl -n monitoring rollout status deployment/host-metrics --timeout=120s
```

Expected:

- `apps` is `Ready: True`.
- The `monitoring` namespace exists.
- A `host-metrics-script-<hash>` ConfigMap exists.
- The Deployment has 1 available replica.
- The pod is `Running` and `Ready`, and `kubectl -n monitoring get pod -o wide` shows `NODE` equal
  to `dietpi`.
- The Service is `ClusterIP`.

If the pod is `Pending`, check the node selector and the control-plane toleration. If it is
`ContainerCreating`, check the hostPath mounts and events.

### 3. Verify the endpoint from the Home Assistant namespace

Use the Home Assistant pod's Python, or a one-off curl pod:

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://host-metrics.monitoring.svc.cluster.local:9100/metrics', timeout=5).read().decode())"
```

Optional one-off curl pod:

```bash
kubectl -n home-assistant run host-metrics-check --rm -it --restart=Never \
  --image=curlimages/curl:8.10.1 -- \
  http://host-metrics.monitoring.svc.cluster.local:9100/metrics
```

Expected: HTTP 200 and a Prometheus text body containing:

- `host_metrics_temperature_available`
- `host_system_temperature_celsius` (when the host has a usable sensor)
- `host_memory_total_bytes`
- `host_memory_available_bytes`
- `host_memory_used_bytes`
- `host_memory_usage_percent`
- `host_filesystem_size_bytes{mountpoint="/"}`
- `host_filesystem_available_bytes{mountpoint="/"}`
- `host_filesystem_used_bytes{mountpoint="/"}`
- `host_filesystem_usage_percent{mountpoint="/"}`
- `host_network_ipv4_info` (when the host network source is readable)
- `host_battery_status_info` (when the host has a readable battery)
- `host_metrics_battery_available`
- `host_metrics_info`

Also check JSON and readiness:

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://host-metrics.monitoring.svc.cluster.local:9100/ha', timeout=5).read().decode())"

kubectl -n home-assistant exec deploy/home-assistant -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://host-metrics.monitoring.svc.cluster.local:9100/readyz', timeout=5).status)"
```

Expected: the JSON body has the keys documented in `contracts/exporter-api.md`, including
`battery_status` and `battery_statuses`, and `/readyz` returns `200`.

### 4. Verify there is no external exposure

```bash
kubectl -n monitoring get service host-metrics -o jsonpath='{.spec.type}{"\n"}'
kubectl -n monitoring get deployment host-metrics \
  -o jsonpath='{.spec.template.spec.hostNetwork}{"\n"}{.spec.template.spec.hostPID}{"\n"}'
kubectl -n monitoring get deployment host-metrics \
  -o jsonpath='{.spec.template.spec.containers[0].securityContext.privileged}{"\n"}'
kubectl get ingress -A | grep -i host-metrics || echo "no host-metrics ingress"
```

Expected:

- Service type is `ClusterIP`.
- `hostNetwork` is empty or `false`.
- `hostPID` is empty or `false`.
- `privileged` is empty or `false`.
- No Ingress references the exporter.
- The Deployment has no `hostPort`.

Optionally confirm the port is not reachable from the Mac or another tailnet host:

```bash
curl --max-time 3 "http://<dietpi-tailscale-ip>:9100/metrics" || echo "not exposed"
```

Expected: connection failure or timeout. A success here is a security defect.

## P2 — Create the Home Assistant sensors

Follow [contracts/home-assistant-ui.md](./contracts/home-assistant-ui.md) exactly. It covers:

1. Adding the Scrape integration with the `/ha` resource URL.
2. Creating the temperature sensor.
3. Creating the RAM usage sensor.
4. Creating the storage usage sensor.
5. Creating the battery status sensor.
6. Creating the Tailscale IPv4 sensor.
7. Optionally creating the all-IPv4 sensor.
8. Forcing a refresh with the integration's **Reload** action.

There is no scan-interval field in the UI. Home Assistant polls every 10 minutes.

### Verify the UI result

1. Open **Developer Tools > States**.
2. Filter for `dietpi`.
3. Confirm the sensors exist and show values with the expected units.
4. Confirm RAM and storage are between 0 and 100.
5. Confirm the battery status sensor shows `Charging`, `Discharging`, `Full`, `Not charging`, or
   `Unknown`, or is unavailable on a host without a battery.
6. Confirm the Tailscale IPv4 sensor contains a dotted-quad address.
7. Choose **Reload** on the Scrape integration, wait for the refresh, and confirm values update.
8. Optionally add the entities to a dashboard through the UI. Do not add dashboard YAML.

Expected:

- Temperature is numeric on a host with a sensor, or unavailable on a host without one.
- RAM and storage percentages are numeric and update.
- Battery status is the raw kernel state, or unavailable on a host without a battery.
- Tailscale IPv4 is a stable dotted-quad value.
- All-IPv4 lists the active addresses and changes when an interface changes.
- No Home Assistant YAML, HACS, automation, or configuration-repository change was made.

## P3 — Recovery and failure scenarios

### Exporter pod restart

```bash
kubectl -n monitoring delete pod -l app.kubernetes.io/name=host-metrics
kubectl -n monitoring rollout status deployment/host-metrics --timeout=120s
```

Then repeat the endpoint check from P1. Expected: a replacement pod is Ready within 2 minutes and
the endpoint returns HTTP 200. Home Assistant sensors recover at the next poll or after **Reload**;
no sensor reconfiguration is needed.

### Exporter down

```bash
kubectl -n monitoring scale deployment/host-metrics --replicas=0
```

Wait for at least one Home Assistant poll (10 minutes) or choose **Reload**. Expected: the sensors
become **unavailable**, not stale or zero. Restore:

```bash
kubectl -n monitoring scale deployment/host-metrics --replicas=1
kubectl -n monitoring rollout status deployment/host-metrics --timeout=120s
```

Flux will also restore the replica count if it reconciles while scaled to zero. Expected: sensors
recover at the next poll.

### Node reboot

Coordinate a maintenance window, then reboot `dietpi` through the documented host procedure. After
the node returns:

```bash
kubectl get nodes
flux get kustomizations apps
kubectl -n monitoring get pod -o wide
kubectl -n monitoring rollout status deployment/host-metrics --timeout=180s
```

Repeat the endpoint check. Expected: the node is Ready, Flux reconciles the workload, the pod is
Ready on `dietpi`, the endpoint works, and the IPv4 metrics reflect the current interfaces. Home
Assistant recovers without reconfiguration.

### Host has no temperature sensor

Do not manufacture a value. Verify:

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://host-metrics.monitoring.svc.cluster.local:9100/ha', timeout=5).read().decode())"
```

Expected: `temperature_c` is `null`, `host_metrics_temperature_available` is `0`, and the other
metrics are present. The Home Assistant temperature sensor's availability template makes it
unavailable. Memory, storage, IP, and battery sensors continue to work.

The absent-temperature path is also covered by the exporter unit tests with fixture directories, so
it can be checked without removing hardware.

### Host has no battery, or the battery status is unreadable

Do not manufacture a value. Verify:

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  python3 -c "import urllib.request; print(urllib.request.urlopen('http://host-metrics.monitoring.svc.cluster.local:9100/ha', timeout=5).read().decode())"
```

Expected: `battery_status` is `null`, `battery_statuses` is an empty array,
`host_metrics_battery_available` is `0`, and the other metrics are present. The Home Assistant
battery status sensor's availability template makes it unavailable. Memory, storage, temperature,
and IP sensors continue to work.

When a battery exists, verify that `/metrics` contains `host_battery_status_info` with the raw
kernel status and that the Home Assistant sensor shows `Charging`, `Discharging`, `Full`,
`Not charging`, or `Unknown`. Change AC power state if practical and confirm the sensor updates at
the next poll. The absent-battery and status-selection paths are also covered by exporter unit
tests with fixture directories.

### Host path permissions or missing path

Check the exporter logs and events:

```bash
kubectl -n monitoring logs deployment/host-metrics
kubectl -n monitoring get events --sort-by=.lastTimestamp | tail -30
kubectl -n monitoring get pod -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{range .status.containerStatuses[*]}{.state}{"\n"}{end}{end}'
```

Expected failure behavior:

- A missing hostPath mount prevents the pod from starting; the event names the path.
- An unreadable `/host/proc/meminfo` or `/host/root` makes `/readyz` return 503 and the pod does not
  become Ready.
- An unreadable hwmon input only removes that temperature reading; the other metrics remain.
- An unreadable `/host/proc/1/net` only removes the IP metrics; the other metrics remain.
- Do not "fix" permissions by making the container privileged or running it as root. Fix the host
  path or document the limitation first.

### Multiple interfaces or changing IPs

1. Compare `/ha` `ipv4_addresses` with the host's active interfaces.
2. Confirm the Tailscale address is the one with `interface: "tailscale0"` and
   `tailscale: true`.
3. If an interface is added or removed, choose **Reload** on the Scrape integration and confirm the
   all-IPv4 sensor changes while the Tailscale sensor remains stable.
4. If the Tailscale interface is down, the Tailscale sensor becomes unavailable and recovers when
   `tailscale0` returns.

## Done criteria

- [ ] `./scripts/validate.sh` passes (or skipped checks are explicitly understood).
- [ ] Flux reconciled the exporter and the pod is Ready on `dietpi`.
- [ ] `/metrics`, `/ha`, and `/readyz` are reachable from the `home-assistant` namespace.
- [ ] The required metric families are present.
- [ ] The Home Assistant UI steps produced updating sensors.
- [ ] The exporter recovered after a pod restart.
- [ ] The documented behavior for no temperature sensor, no battery, exporter down, node reboot,
      and hostPath failure was observed or justified by tests.
- [ ] The battery status sensor shows the raw kernel state and updates on a real power-state
      change, or is unavailable on a host without a battery.
- [ ] No external exposure, secrets, Home Assistant YAML, HACS, or Home Assistant repository
      changes were introduced.

## Operator documentation

The durable operator guide is [`docs/11-host-metrics.md`](../../docs/11-host-metrics.md). This
quickstart is for verification; the operator guide is the long-lived reference.
