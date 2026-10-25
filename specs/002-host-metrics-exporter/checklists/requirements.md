# Specification Quality Checklist: Host Metrics Exporter and Home Assistant Integration

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-25
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- The specification names Flux, Kubernetes, ClusterIP, the `monitoring` and `home-assistant`
  namespaces, `dietpi`, the internal DNS URL, and Home Assistant UI integration because they are
  fixed scope constraints and observable contracts chosen by the owner, not design leakage. The
  measurement semantics, units, failure behavior, and measurable outcomes remain independent of the
  exporter implementation.
- Planning selected a small custom Python stdlib exporter because Node Exporter does not expose host
  IPv4 addresses without host networking. The plan fixes the exact metric names and endpoint shapes.
- The metric contract defines required semantics, units, labels, and absence behavior. The exact
  emitted metric names are fixed in `contracts/exporter-api.md` and must also appear in the
  feature's operator documentation.
- No clarification markers remain. Planning confirmed that the built-in Scrape integration is
  UI-configurable and can read the exporter's JSON representation with a selector, value template,
  and availability template. Its UI does not expose a scan interval, so the documented cadence is
  the integration default of 10 minutes; faster polling would require YAML or HACS and remains out
  of scope.
- The audience is the household operator, not an external business stakeholder; "user value" is
  expressed as visible household measurements, predictable degradation, and documented recovery.
- Charging status was clarified to come from the host's Linux `power_supply` battery interface.
  The spec now covers the raw `Charging`, `Discharging`, `Full`, `Not charging`, and `Unknown`
  states, multiple batteries, an absent battery, and an unreadable status file. NUT/UPS, battery
  percentage, health, and runtime remain out of scope.
