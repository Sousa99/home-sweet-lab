# 14 — Agent workload

Status: manifests added to Flux; awaiting first reconciliation on the cluster.

The Home Sweet Home agent (`home-sweet-home-agent`) runs as a Flux-managed workload in the `agent`
namespace. This repository owns the Deployment, Service, configuration, and image automation only.
The agent runtime, conversation behavior, and LLM orchestration belong to
[`home-sweet-home-agent`](https://github.com/Sousa99/home-sweet-home-agent).

## What runs

| Object | Purpose |
| ------ | ------- |
| `agent` Namespace | Workload boundary for the agent |
| `agent` Deployment | One agent pod on `dietpi` (linux/amd64) |
| `agent` Service | ClusterIP on port 3400 for in-cluster consumers |
| `agent-config` ConfigMap | Non-secret settings, module MCP URLs, Home Assistant MCP URL |
| `agent-auth` Secret | Caller token hash map (manual) |
| `agent-llm` Secret | LLM API key (manual) |
| `agent-home-assistant` Secret | Home Assistant long-lived token (manual, optional) |
| `agent` image automation | ImageRepository, ImagePolicy, ImageUpdateAutomation in `flux-system` |

The Service is cluster-internal. There is no Ingress, load balancer, node port, host port, or public
exposure. `/conversation` and `/health` are reachable only from inside the cluster.

## Configuration

Non-secret settings live in `apps/agent/configmap.yaml`:

| Key | Value |
| --- | ----- |
| `NODE_ENV` | `production` |
| `AGENT_HOST` | `0.0.0.0` |
| `AGENT_PORT` | `3400` |
| `LOG_LEVEL` | `info` |
| `LOG_REDACT` | `true` |
| `MCP_TIMEOUT_MS` | `10000` |
| `LLM_TIMEOUT_MS` | `30000` |
| `LLM_PROVIDER` | `openai-compatible` |
| `LLM_BASE_URL` | `https://opencode.ai/inference/go/openai/v1` |
| `LLM_MODEL` | `deepseek-v4.1-flash` |
| `CONFIRMATION_TTL_MS` | `120000` |
| `AGENT_MAX_TOOL_ITERATIONS` | `4` |
| `AGENT_MAX_TOOL_RESULT_CHARS` | `8000` |
| `AGENT_UNKNOWN_TOOL_POLICY` | `destructive` |
| `BUS_MCP_URL` | `http://bus-catcher-mcp.dashboard.svc.cluster.local:3001/mcp` |
| `FLIGHTS_MCP_URL` | `http://fly-over-tracker-mcp.dashboard.svc.cluster.local:3001/mcp` |
| `TASKS_MCP_URL` | `http://procrastinator-tracker-mcp.dashboard.svc.cluster.local:3001/mcp` |
| `WEATHER_MCP_URL` | `http://weather-psychic-mcp.dashboard.svc.cluster.local:3001/mcp` |
| `HOME_ASSISTANT_MCP_URL` | `http://home-assistant.home-assistant.svc.cluster.local:8123/api/mcp` |

Change non-secret settings in Git, let Flux reconcile, and delete the pod so the ConfigMap values
are re-read. Do not use `kubectl rollout restart`; delete the pod and let the ReplicaSet recreate it.

## Secrets

Flux does not manage Secrets. Create them before expecting the pod to become Ready. Never commit
the values.

### Caller tokens (`agent-auth`)

Generate the hash map in `home-sweet-home-agent`:

```bash
cd ~/Desktop/code/home-sweet-home/home-sweet-home-agent
pnpm token:generate -- --caller-id <caller> --permissions read,write,destructive --out tokens.json
```

The generated file contains only the hash map. Only that map goes into the cluster; deliver the
plaintext bearer token printed once by the generator to the caller separately. The Deployment reads
`AGENT_AUTH_TOKENS`, which expects a single-line JSON object, so compact the pretty-printed file and
create the Secret:

```bash
python3 -c 'import json; print(json.dumps(json.load(open("tokens.json")), separators=(",", ":")))' \
  > tokens.inline.json
kubectl -n agent create secret generic agent-auth \
  --from-file=AGENT_AUTH_TOKENS=tokens.inline.json \
  --dry-run=client -o yaml | kubectl apply -f -
rm tokens.inline.json
```

The Deployment exposes it as `AGENT_AUTH_TOKENS`. Startup fails intentionally when no caller tokens
are configured.

To use the mounted-file alternative instead, store the pretty-printed map under a `tokens.json` key,
mount the Secret at a fixed path, and set `AGENT_TOKENS_FILE` to that path. Do not set both forms
with different contents.

### LLM key (`agent-llm`)

```bash
kubectl -n agent create secret generic agent-llm \
  --from-literal=LLM_API_KEY='<llm-api-key>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Required for the remote OpenAI-compatible endpoint. Without it the pod can start but readiness stays
`503`.

### Home Assistant token (`agent-home-assistant`)

```bash
kubectl -n agent create secret generic agent-home-assistant \
  --from-literal=HOME_ASSISTANT_MCP_TOKEN='<long-lived-access-token>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

Optional. If the Secret or key is absent, the Deployment leaves `HOME_ASSISTANT_MCP_TOKEN` unset,
the agent reports the Home Assistant source unavailable, and the rest of the agent keeps working.

### Image pull

`ghcr.io/sousa99/home-sweet-home-agent` is public, so no pull Secret is required. If the package is
made private, create a `read:packages` credential and a documented image pull Secret, then add
`imagePullSecrets` to the pod template. Never commit the token.

## Deploy and verify

```bash
flux reconcile kustomization apps --with-source
kubectl -n agent get deploy,po,svc
kubectl -n agent rollout status deployment/agent --timeout=5m
```

Probes are unauthenticated and do no network I/O:

- `GET /healthz` returns `200` while the process is alive.
- `GET /readyz` returns `200` when the LLM provider is ready and the agent is not draining, otherwise
  `503`. It stays `200` when MCP sources are down.

Verify from inside the cluster with a temporary client pod:

```bash
kubectl -n agent run agent-probe --rm -it --restart=Never --image=curlimages/curl -- \
  curl -sS -o /dev/null -w '%{http_code}\n' http://agent.agent.svc.cluster.local:3400/healthz
kubectl -n agent run agent-probe --rm -it --restart=Never --image=curlimages/curl -- \
  curl -sS -o /dev/null -w '%{http_code}\n' http://agent.agent.svc.cluster.local:3400/readyz
```

`GET /health` still requires a bearer token:

```bash
kubectl -n agent run agent-probe --rm -it --restart=Never --image=curlimages/curl -- \
  curl -sS -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: Bearer <plaintext-token>" http://agent.agent.svc.cluster.local:3400/health
```

Expected: `/healthz` and `/readyz` return `200`; `/health` returns `401` without a token and `200`
with a valid token. From another pod, the module MCP URLs resolve and reach
`dashboard.svc.cluster.local:3001/mcp`.

## Image updates

Flux scans `ghcr.io/sousa99/home-sweet-home-agent` every 5 minutes, selects tags matching
`^main-[0-9]{14}-[0-9a-f]{7}$` in alphabetical ascending order, and updates the image setter in
`apps/agent/deployment.yaml`. A new matching tag produces a commit from `fluxcdbot` and a rollout.

Check the automation:

```bash
kubectl -n flux-system get imagerepository,imagepolicy,imageupdateautomation | grep agent
kubectl -n agent get deploy agent -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
```

## Troubleshooting

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| `CreateContainerConfigError` for `agent-auth` or `agent-llm` | Required Secret or key missing | Create the Secret and delete the pod |
| Pod starts but `/readyz` returns `503` | LLM key absent, provider unreachable, or draining | Check `agent-llm` and provider reachability; inspect logs |
| Home Assistant source unavailable | Optional Secret missing or Home Assistant down | Create `agent-home-assistant` or leave it; readiness stays `200` |
| Module tools unavailable | Dashboard MCP Service down or renamed | Check `kubectl -n dashboard get svc`; readiness stays `200` |
| `ImagePullBackOff` | GHCR package became private or tag removed | Restore public access or add a pull Secret; revert the image pin |
| `CrashLoopBackOff` at startup | Token configuration empty or invalid | Regenerate the hash map and recreate `agent-auth` |
| New tag not rolled out | Tag does not match the pattern | Check `kubectl -n flux-system describe imagepolicy agent` |
| Probe failures only on `/readyz` | Agent draining or LLM not ready | Expected during shutdown; investigate if persistent |

## Recovery

- Pod deleted or node rebooted: Flux and the ReplicaSet recreate the pod; no manual `kubectl apply`.
- Secret lost after a cluster rebuild: recreate `agent-auth`, `agent-llm`, and optionally
  `agent-home-assistant` from the password manager before expecting readiness.
- Bad image: revert the image tag in `apps/agent/deployment.yaml`, commit, and let Flux reconcile.
- Bad configuration: revert `apps/agent/configmap.yaml`, commit, and delete the pod.
- `SIGTERM` drains for up to 5 seconds; `terminationGracePeriodSeconds` is 20 so rollouts and node
  shutdowns complete cleanly.

## Boundaries

- The agent is stateless; no PVC and no backup are required.
- No public exposure, ingress, SSO, or probe authentication.
- The module REST APIs and MCP services remain owned by the dashboard stack.
- The Home Assistant conversation adapter and proactive notifications remain future features in
  `home-sweet-home-agent`.
