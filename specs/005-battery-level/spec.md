# Feature Specification: Battery Level Percentage

**Feature Branch**: `main`

**Created**: 2026-11-06

**Status**: Draft

**Input**: User description: "currently we export from the host the battery status (full, charging, discharging). Now i also want battery level, so the actual percentage, I know this can be retrieved from the host using acpi command already installed, at least like this."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - See battery percentage in Home Assistant (Priority: P1)

The household operator already sees the host battery charging state on the
`home-sweet-lab-server` Home Assistant device. They now want to see how full the battery is as a
percentage that updates with the rest of the host metrics.

**Why this priority**: The battery percentage is the requested capability. Without it the feature
delivers no value, even if the underlying export is otherwise correct.

**Independent Test**: Reconcile the exporter, open the `home-sweet-lab-server` device in Home
Assistant, and confirm a battery-level entity exists and shows the same percentage the host reports.

**Acceptance Scenarios**:

1. **Given** the host has a readable battery, **When** the exporter publishes host metrics,
   **Then** a battery-level entity appears on the `home-sweet-lab-server` device with a numeric
   percentage between 0 and 100.
2. **Given** the host battery level changes, **When** the next publishing cycle completes,
   **Then** the Home Assistant entity shows the new percentage without manual refresh.
3. **Given** the battery status and battery level are both readable, **When** the operator views
   the device, **Then** both the existing battery-status entity and the new battery-level entity
   are present and represent the same physical battery.

---

### User Story 2 - Use battery level from the HTTP exporter (Priority: P2)

The operator or a debugging tool reads the exporter's HTTP output and expects the battery
percentage to be available alongside the existing battery status.

**Why this priority**: The HTTP endpoints are the documented debugging path and must stay consistent
with the MQTT/Home Assistant data, but they are secondary to the operator-facing sensor.

**Independent Test**: Query the exporter's HTTP endpoints and confirm the battery percentage is
present in both the metric output and the flat JSON output.

**Acceptance Scenarios**:

1. **Given** a readable host battery, **When** the metrics endpoint is requested, **Then** the
   response contains a battery-level metric for each readable battery.
2. **Given** a readable host battery, **When** the flat JSON endpoint is requested, **Then** the
   response contains the preferred battery's level and a per-battery level for every battery.

---

### User Story 3 - Stay usable when a battery cannot report its level (Priority: P3)

The household operator has a host without a battery, or with a battery that reports status but not
level. The exporter keeps working and only the affected value is unavailable.

**Why this priority**: The lab is a single-node household cluster; an unsupported or partially
readable battery must not break the rest of the host metrics.

**Independent Test**: Run the exporter against a host with no battery and against a battery whose
level cannot be read, and confirm the other sensors and endpoints are unaffected.

**Acceptance Scenarios**:

1. **Given** the host has no battery, **When** metrics are published, **Then** no battery-level
   entity shows a value, the battery source is reported unavailable, and all other host metrics
   continue.
2. **Given** a battery reports status but not level, **When** metrics are published, **Then** the
   battery-status entity still shows its state, the battery-level entity has no value, and the
   exporter remains ready.
3. **Given** a host with multiple batteries, **When** metrics are published, **Then** each battery's
   level is available and the preferred battery's level matches the single Home Assistant entity.

---

### Edge Cases

- The host has no battery at all; battery-level data is absent and the battery source is unavailable.
- A battery reports a status but no readable level; status remains available and level is absent.
- A battery reports an out-of-range or non-numeric level; numeric values are constrained to 0–100
  and non-numeric values are treated as absent rather than shown as a misleading number.
- The host has multiple batteries; all levels are exported and the preferred battery drives the
  single Home Assistant entity.
- The battery level is exactly 0% or 100%; both are valid values and must not be treated as missing.
- The battery changes state (for example, charging to full) between collection cycles; status and
  level stay consistent for the same reading.
- The host reboots or the exporter restarts; the battery level returns automatically with the rest
  of the device metrics and no Home Assistant reconfiguration is needed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The exporter MUST collect the host battery level as a percentage for every readable
  battery.
- **FR-002**: The battery level MUST be exposed through the existing metrics output as a numeric
  measurement associated with the same battery device identity used for battery status.
- **FR-003**: The flat JSON output MUST include the preferred battery's level and a level value for
  each battery entry in the per-battery list.
- **FR-004**: The MQTT state payload MUST include the preferred battery level and per-battery level
  values, following the same key and structure conventions as battery status.
- **FR-005**: Home Assistant MUST present a new battery-level entity on the existing
  `home-sweet-lab-server` device using the percentage unit, a battery-appropriate device class,
  and measurement state class.
- **FR-006**: The battery-level entity MUST be available only when the battery source is available
  and MUST become unavailable with the existing battery source availability behavior.
- **FR-007**: The existing battery-status entity and behavior MUST remain unchanged.
- **FR-008**: When no battery level can be read, the exporter MUST continue to serve all other
  metrics, remain ready, and represent the missing level as absent rather than zero.
- **FR-009**: The exporter MUST NOT require host-level command execution or privileged access
  beyond its existing read-only host access to obtain the battery level.
- **FR-010**: The battery percentage MUST be constrained to the valid range of 0 to 100 inclusive.
- **FR-011**: Repository documentation and the MQTT discovery contract MUST be updated to describe
  the new battery-level metric, JSON key, entity, topic, ACL entry, and verification steps.
- **FR-012**: Unit tests MUST cover a readable level, a battery without a readable level, no
  battery, multiple batteries, and the resulting metric, JSON, MQTT discovery, and state output.

### Key Entities

- **Battery reading**: A host battery device with a name, charging status, optional level
  percentage, source path, and preferred flag.
- **Battery-level measurement**: The percentage value exported for a battery, exposed as a metric,
  a flat JSON value, and a Home Assistant entity.
- **Battery-level entity**: The new Home Assistant sensor on the `home-sweet-lab-server` device.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The `home-sweet-lab-server` device shows a battery-level percentage within 60 seconds
  of the exporter publishing state, with no Home Assistant reconfiguration beyond receiving the new
  discovery message.
- **SC-002**: For a host with a readable battery, 100% of publishing cycles produce a numeric battery
  level between 0 and 100 in the metric, flat JSON, MQTT state, and Home Assistant entity.
- **SC-003**: A host with no battery, or a battery with no readable level, produces no false
  percentage value and leaves every unrelated host metric working.
- **SC-004**: The exporter remains Ready and the main availability topic remains online while a
  battery level is missing.
- **SC-005**: Existing battery-status behavior is unchanged: its entity, values, and availability
  match pre-change behavior in all tested cases.
- **SC-006**: Operators can verify the new value using the documented commands and expected output.

## Out of Scope

- Battery health, cycle count, runtime remaining, power draw, or NUT/UPS integration.
- Changing the battery-status values or mapping them to binary charging/discharging states.
- A new host service, agent, or command-execution path for battery collection.
- Home Assistant YAML, HACS, automations, scenes, dashboards, or configuration-repository changes.
- Changing the existing device identity, broker, or non-battery MQTT entities.

## Dependencies

- The existing `host-metrics` exporter, its host mounts, and its MQTT publishing path.
- A host battery source that exposes both status and level, or a documented fallback when only
  status is available.
- Home Assistant's MQTT integration and the existing `home-sweet-lab-server` device.
- The existing `mosquitto-auth` Secret and broker ACLs.

## Assumptions

- The battery level is a whole-number percentage reported by the host; fractional percentages are
  not required.
- The host already exposes battery information to the exporter through its existing read-only host
  access, so no new host package or privileged mode is needed.
- The `acpi` tool can report the battery percentage on the host, but the feature only requires the
  percentage outcome; the existing read-only host source may be used directly.
- Multiple batteries keep the existing preferred-battery rule: the first readable device is
  preferred and drives the single Home Assistant entity.
- The new entity belongs to the same device and source-availability group as battery status.
- Home Assistant receives discovery automatically; the operator does not create the entity manually.
