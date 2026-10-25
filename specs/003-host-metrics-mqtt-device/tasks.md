# Tasks: MQTT Device Grouping for Host Metrics

**Input**: `specs/003-host-metrics-mqtt-device/`
**Prerequisites**: `spec.md`, `plan.md`, `contracts/mqtt-discovery.md`

## Phase 1: Exporter MQTT

- [X] T001 Add `apps/host-metrics/mqtt_discovery.py` with the `home-sweet-lab-server` device block, six entity definitions, discovery topics, state/availability topics, and exact entity IDs.
- [X] T002 Add `apps/host-metrics/mqtt_publisher.py` with paho MQTT connection, LWT, retained discovery/state/availability, HA birth handling, reconnect, and 30-second publishing.
- [X] T003 Update `apps/host-metrics/exporter.py` to start MQTT when `MQTT_HOST` is set while keeping the HTTP endpoints.
- [X] T004 Add paho-free discovery tests and paho-gated publisher tests in `apps/host-metrics/test_mqtt_publisher.py`; extend `apps/host-metrics/test_exporter.py` for the new naming contract.
- [X] T005 Add `apps/host-metrics/requirements.txt` and `apps/host-metrics/Dockerfile`; build the image locally and run the tests inside it.

## Phase 2: Broker

- [X] T006 Add `apps/host-metrics/mqtt/configmap.yaml` with `mosquitto.conf` and the two-user ACL.
- [X] T007 Add `apps/host-metrics/mqtt/deployment.yaml` with pinned Mosquitto, non-root/read-only security, TCP probes, resources, and a projected source volume copied into an emptyDir by an init container (avoids Mosquitto symlink rejection).
- [X] T008 Add `apps/host-metrics/mqtt/service.yaml` as ClusterIP port 1883 and `apps/host-metrics/mqtt/kustomization.yaml`.
- [X] T009 Add the broker resources to `apps/host-metrics/kustomization.yaml`.
- [X] T010 Document and validate the manual `mosquitto-auth` Secret format in `docs/12-host-metrics-mqtt.md`.

## Phase 3: Image and deployment

- [X] T011 Add `.github/workflows/publish-host-metrics.yml` to test, build, and publish the exporter image to GHCR with immutable tags.
- [X] T012 Add `apps/host-metrics/image-automation.yaml` for ImageRepository/ImagePolicy/ImageUpdateAutomation.
- [X] T013 Update `apps/host-metrics/deployment.yaml` to use the custom image, Secret-based MQTT env, and remove the ConfigMap script volume.
- [X] T014 Update `apps/host-metrics/kustomization.yaml` to remove `configMapGenerator`; keep the broker resources.
- [X] T015 Run `kubectl kustomize apps` and `./scripts/validate.sh`; fix YAML, schema, lint, secret-scan, and test failures.

## Phase 4: Documentation and Home Assistant

- [X] T016 Create `docs/12-host-metrics-mqtt.md` with broker, Secret, ACL, MQTT UI, device/entity contract, migration, and recovery.
- [X] T017 Update `docs/11-host-metrics.md` to mark Scrape as legacy and point to the MQTT path.
- [X] T018 Update `README.md` and `docs/README.md` with document 12 and the MQTT architecture.
- [X] T019 Update `docs/09-limitations.md` with MQTT auth, no TLS, ephemeral broker, custom image, and no Scrape primary path.
- [X] T020 Add the task list and feature artifacts to the repository review set.

## Phase 5: Verification

- [X] T021 Build the custom image and run the exporter + a local Mosquitto broker; verify discovery, state, availability, LWT, and HA birth republish.
- [X] T022 Commit/push (when explicitly approved) and let the GitHub Actions workflow publish the first GHCR image.
- [X] T023 Reconcile Flux; verify the broker and exporter are Ready, the Secret exists, and ACLs allow only the documented topics.
- [X] T024 Verify retained discovery/state with `mosquitto_sub`, including the one-device device block and six entity topics.
- [ ] T025 Add the Home Assistant MQTT integration via the UI; verify one `home-sweet-lab-server` device with six entities and updates within 60 seconds.
- [ ] T026 Remove the legacy Scrape integration if present; delete orphaned entities; verify no duplicates.
- [ ] T027 Test exporter restart/LWT, broker restart, HA restart, Secret failure, and node reboot; record results in `docs/12-host-metrics-mqtt.md`.
- [X] T028 Security review: no external MQTT, no plaintext credentials in Git, no privileged mode, no Home Assistant repo changes.
- [X] T029 Final validation and diff review; commit/push when explicitly requested.

## Pending / Blocked

- T025/T026 require the operator to perform the Home Assistant MQTT UI steps and remove legacy Scrape.
- T027 requires the Secret-failure and coordinated node-reboot drills.