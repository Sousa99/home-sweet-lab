# Quickstart: Workload Image Updates

This guide updates the two workload images, validates the manifests, reconciles through Flux, proves
the runtime behavior, records the Home Assistant seeding decision, and documents rollback. It is a
run/validation guide; detailed expected outputs are in
[contracts/runtime-verification.md](./contracts/runtime-verification.md).

## Prerequisites

- Repository checkout at the tracked branch, with `kubectl` and `flux` configured for the `dietpi`
  cluster.
- `kubectl`, `kubeconform`, `yamllint`, and optionally `gitleaks` available for `scripts/validate.sh`.
- Both target images public in GHCR:
  - `ghcr.io/sousa99/bus-catcher-backend:0.4.0`
  - `ghcr.io/sousa99/home-sweet-home-home-assistant:main-20261109193052-7e131ee`
- Current bus-catcher and Home Assistant state still on their PVCs, and no backup or restore operation
  in progress.
- The previous Home Assistant tag remains published for rollback.

## 1. Record the starting state

```bash
kubectl -n dashboard get deploy bus-catcher-rest bus-catcher-mcp \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}{end}'
kubectl -n home-assistant get deploy home-assistant \
  -o jsonpath='{range .spec.template.spec.initContainers[*]}{.name}{"\t"}{.image}{"\n"}{end}{.spec.template.spec.containers[0].name}{"\t"}{.spec.template.spec.containers[0].image}{"\n"}'
kubectl -n home-assistant exec deploy/home-assistant -- \
  sh -c 'ls -l /config/.storage/core.config_entries /config/zigbee.db /config/home-assistant_v2.db 2>/dev/null'
```

Record the bus `lastRefresh`/`feedVersion` from `/api/status` before the change. These are the
baselines for the freshness and persistence checks.

## 2. Update the image pins

Edit these files and change only the image references:

| File | From | To |
| ---- | ---- | -- |
| `apps/dashboard/bus-catcher-rest.yaml` | `bus-catcher-backend:0.3.0` | `bus-catcher-backend:0.4.0` |
| `apps/dashboard/bus-catcher-mcp.yaml` | `bus-catcher-backend:0.3.0` | `bus-catcher-backend:0.4.0` |
| `apps/home-assistant/deployment.yaml` (4 references) | `...:main-20261025090622-dd38b4b` | `...:main-20261109193052-7e131ee` |

Keep every Home Assistant image marker:

```yaml
# {"$imagepolicy": "flux-system:home-assistant"}
```

Do not change probes, resources, volumes, commands, environment variables, or the bus memory limit in
this step. The 0.4.0 defaults (`SCHEDULE_AUTO_REFRESH=true`, 15-minute check interval) are used as-is.

## 3. Validate locally

```bash
./scripts/validate.sh
```

Expected: rendering, `kubeconform`, yamllint, Python tests, shell tests, and gitleaks all pass. If
`kubeconform`, `yamllint`, or `gitleaks` is missing, install it rather than accepting the skip for
the final validation record.

Also confirm the rendered pins:

```bash
kubectl kustomize apps/dashboard | grep -n 'bus-catcher-backend'
kubectl kustomize apps/home-assistant | grep -n 'home-sweet-home-home-assistant'
```

## 4. Commit and reconcile

```bash
git add apps/dashboard/bus-catcher-rest.yaml apps/dashboard/bus-catcher-mcp.yaml \
  apps/home-assistant/deployment.yaml
git commit -m 'chore: update bus-catcher to 0.4.0 and home-assistant image'
git push
flux reconcile source git flux-system
flux reconcile kustomization apps --with-source
```

Then wait for the rollouts:

```bash
kubectl -n dashboard rollout status deployment/bus-catcher-rest --timeout=10m
kubectl -n dashboard rollout status deployment/bus-catcher-mcp --timeout=10m
kubectl -n home-assistant rollout status deployment/home-assistant --timeout=10m
```

Expected: all three Deployments complete their rollouts and their pods are Ready with the new image
references.

## 5. Verify bus-catcher 0.4.0

```bash
kubectl -n dashboard port-forward svc/bus-catcher-rest 3000:3000
curl -sS http://127.0.0.1:3000/api/health
curl -sS http://127.0.0.1:3000/api/status
curl -sS -X POST 'http://127.0.0.1:3000/api/refresh?force=true'
```

Poll `/api/status` until `refreshing` is `false`. Expected: `lastRefresh` advances, `refreshError` is
null or absent, and the schedule is fresh. The ingest may take several minutes; the health endpoint
must stay responsive.

Confirm no OOMKill:

```bash
kubectl -n dashboard get pod -l app.kubernetes.io/name=bus-catcher,app.kubernetes.io/component=rest \
  -o jsonpath='{.items[*].status.containerStatuses[*].lastState.terminated.reason}{"\n"}'
```

Confirm MCP initialize and data consistency using the commands in
[contracts/runtime-verification.md](./contracts/runtime-verification.md#bus-catcher-mcp). Then check
the dashboard proxy path.

## 6. Verify bus persistence

```bash
kubectl -n dashboard delete pod -l app.kubernetes.io/name=bus-catcher,app.kubernetes.io/component=rest
kubectl -n dashboard rollout status deployment/bus-catcher-rest --timeout=10m
curl -sS http://127.0.0.1:3000/api/status
```

Expected: the replacement pod is Ready, the recorded `lastRefresh`/`feedVersion` survive, and the
configured stop list is unchanged.

## 7. Verify Home Assistant rollout and the seeding decision

```bash
kubectl -n home-assistant rollout status deployment/home-assistant --timeout=10m
kubectl -n home-assistant logs deploy/home-assistant -c seed-config
kubectl -n home-assistant logs deploy/home-assistant -c restore-state
kubectl -n home-assistant logs deploy/home-assistant -c configure-http
```

Expected: all init containers exit `0`; `restore-state` reports no newly applied bundle because no
archive was uploaded. Then verify tracked configuration and preserved runtime state:

```bash
kubectl -n home-assistant exec deploy/home-assistant -- \
  sh -c 'test -f /config/custom_components/home_sweet_home_agent/manifest.json && echo component-ok'
kubectl -n home-assistant exec deploy/home-assistant -- \
  sh -c 'test -f /config/.storage/core.config_entries && echo storage-ok'
kubectl -n home-assistant exec deploy/home-assistant -- \
  sh -c 'test -f /config/zigbee.db && echo zigbee-ok'
```

Expected conclusion: the normal `seed-config` init container was sufficient; no separate state seed,
state-bundle upload, or manual `/config` copy was required. If any new tracked file is missing, or if
existing `.storage`/database/Zigbee state is missing, stop and treat it as a failed rollout.

The custom integration's config entry and the Assist pipeline selection remain manual UI steps in
`home-sweet-home-home-assistant`. They live in `.storage`, are not automated here, and are not
required for Home Assistant itself to become Ready.

## 8. Record the result in the docs

Update:

- `docs/06-home-assistant.md`: current image pin, seed decision, verification date, integration
  availability, rollback reference.
- `docs/13-dashboard.md`: bus-catcher `0.4.0` pin, the refreshed bus data, and the resolved OOM
  caveat. Make the memory-limit text match the 10 GiB manifest.

Include the actual observed values, not the expected ones. Do not add secrets, tailnet identifiers,
database contents, or backup archives.

## 9. Re-run validation and reconcile the docs

```bash
./scripts/validate.sh
git add docs/06-home-assistant.md docs/13-dashboard.md
git commit -m 'docs: record workload image updates and home-assistant seed result'
git push
flux reconcile source git flux-system
```

## 10. Rollback if needed

```bash
git revert <pin-commit>
git push
flux reconcile source git flux-system
flux reconcile kustomization apps --with-source
kubectl -n dashboard rollout status deployment/bus-catcher-rest --timeout=10m
kubectl -n dashboard rollout status deployment/bus-catcher-mcp --timeout=10m
kubectl -n home-assistant rollout status deployment/home-assistant --timeout=10m
```

Expected: bus returns to `0.3.0`, Home Assistant returns to
`main-20261025090622-dd38b4b`, all workloads become Ready, and the PVC data remains intact. Do not use
`kubectl set image` as the permanent rollback.
