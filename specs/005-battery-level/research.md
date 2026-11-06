# Phase 0 Research: Battery Level Percentage

**Feature**: `specs/005-battery-level`
**Date**: 2026-11-06
**Status**: Complete; no `NEEDS CLARIFICATION` remains.

## R1 — Source of the battery percentage

### Decision

Read the percentage from the Linux `power_supply` class file
`/host/sys/class/power_supply/<device>/capacity` for each battery discovered through the existing
`type`/`status` files.

### Rationale

- The exporter already mounts the host `/sys` read-only at `/host/sys` and already enumerates
  `power_supply` directories to read `type` and `status`.
- `capacity` is the kernel's normalized integer percentage for a battery and is present on the
  current `BAT0` host source.
- `acpi -b` itself reads the same `power_supply` data; invoking it would add a process execution
  path, an extra package in the image, and fragile human-readable output parsing for no new data.
- No new host mount, package, privilege, or dependency is needed.
- Collecting level in the same pass as status keeps both values consistent for one reading.

### Alternatives considered

| Alternative | Why rejected |
| ----------- | ------------ |
| Run `acpi -b` from the container | Requires `acpi` and its libraries in the image or a host bind mount, adds command execution and parsing, and violates the feature requirement to avoid new host command execution. Supported host already exposes the value through sysfs. |
| Compute from `energy_now` / `energy_full` or `charge_now` / `charge_full` | Units and file availability differ between batteries and drivers; unnecessary when `capacity` exists. |
| Read `capacity_level` (for example `Normal`) | Not a percentage; does not satisfy the requirement. |
| Add NUT/UPS data | Out of scope; adds a service and hardware dependency. |

### Fallback behavior

If `capacity` is missing, unreadable, or non-numeric, the battery reading still exists when
`status` is readable, and `level_percent` is `None`. If `status` is unreadable, the battery is
skipped exactly as today, preserving existing status behavior.

## R2 — Value model and validation

### Decision

Store `level_percent` as an optional integer on `BatteryReading`. Parse the trimmed file contents
as an integer, clamp numeric values to `0..100`, and treat unparseable contents as absent.

### Rationale

- Home Assistant percentage sensors and the kernel report whole percentages; fractional values are
  not required by the spec.
- Clamping prevents a faulty driver value from producing a misleading metric.
- `None` distinguishes "unknown" from a real `0%`; a missing level must not look like an empty
  battery.
- Keeping the field optional avoids breaking snapshots, tests, or fixtures that predate the field.

### Alternatives considered

| Alternative | Why rejected |
| ----------- | ------------ |
| Required float percentage | Breaks hosts with status-only batteries and conflates unreadable with zero. |
| Send a separate battery entity only when level exists | Adds conditional discovery complexity; Home Assistant already handles an entity whose value template resolves to `None` / unavailable. |
| Validate strictly and drop the battery on a bad capacity value | Would also hide the still-valid status value, violating the unchanged-status requirement. |

## R3 — HTTP and MQTT interface shape

### Decision

Add to the existing interfaces without renaming or removing anything:

- Metric: `host_battery_level_percent{device,path}` with the `capacity` source path.
- Flat JSON: `battery_level_percent` for the preferred battery and `level_percent` in each
  `battery_statuses` entry.
- MQTT discovery: sensor key `battery_level`, entity ID
  `sensor.home_sweet_lab_server_battery_level`, unit `%`, device class `battery`, state class
  `measurement`, icon `mdi:battery`, value template `{{ value_json.battery_level_percent }}`.
- Availability: the existing battery source topic.

### Rationale

- The flat JSON is shared by `/ha` and the MQTT state payload, so one key addition serves both.
- Following the status key naming (`battery_status` / `status` in the per-battery list) keeps the
  payload predictable for operators and templates.
- A separate entity matches Home Assistant convention: status is a text state; level is a numeric
  measurement with a device class.
- Reusing battery-source availability means an absent battery makes both battery entities
  unavailable; an absent level alone leaves status available and the level entity without a value.
- Additive changes preserve the existing public contract and dashboards.

### Alternatives considered

| Alternative | Why rejected |
| ----------- | ------------ |
| Replace the status entity with a combined entity | Destructive change and out of scope; status must remain unchanged. |
| Encode the level inside the status string | Breaks existing text semantics and templates. |
| Publish a separate MQTT state topic for level | Adds a topic and ACL surface without benefit; the shared state payload already carries all values. |

## R4 — Discovery, ACL, and documentation updates

### Decision

Update the broker ACL ConfigMap so the exporter can write and Home Assistant can read
`homeassistant/sensor/home_sweet_lab_server_battery_level/config`. Update the HTTP/MQTT docs,
the limitations list, and the feature contract. The exporter Deployment and image dependencies do
not change.

### Rationale

- MQTT ACLs are explicit per topic; without the new entries the discovery message would be denied.
- Documentation is part of the operator contract in this repository and must name the new metric,
  key, entity, and verification command.
- The `/host/sys` mount and `paho-mqtt` dependency already cover the implementation, so no
  deployment or requirements change is needed.

### Alternatives considered

| Alternative | Why rejected |
| ----------- | ------------ |
| Wildcard discovery write (`homeassistant/sensor/#`) | Broader than necessary; the existing ACL is intentionally explicit. |
| Leave docs unchanged | Fails the repository workflow and the spec's documentation requirement. |

## R5 — Testing strategy

### Decision

Extend the existing `unittest` suite:

- Collection: readable `capacity`, missing capacity, non-numeric capacity, out-of-range capacity,
  multiple batteries, and status-only battery.
- Render: metric family presence/absence, flat JSON preferred and per-battery level, and null level.
- MQTT: discovery message count increases to seven, the new payload has the expected entity ID,
  unit, device class, state class, icon, value template, and battery availability; state includes
  the new key.
- Validation: Kustomize render and kubeconform for `apps/host-metrics`.

### Rationale

- The repository already uses standard-library `unittest`, discovered by the publish workflow, so
  no new test framework is introduced.
- The existing tests exercise the public contracts, which is where regressions matter.

### Alternatives considered

| Alternative | Why rejected |
| ----------- | ------------ |
| Add `pytest` | Unnecessary dependency and inconsistent with the existing suite. |
| Only test the parser | Would miss metric, JSON, discovery, ACL, and documentation regressions. |
