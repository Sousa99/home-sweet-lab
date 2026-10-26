# Contract: Internal MCP Services

**Scope**: Cluster-internal MCP endpoints consumed by `home-sweet-home-agent` and other in-cluster
clients.

## Endpoints

All endpoints use streamable HTTP at `/mcp` on port `3001`. The DNS names are stable and live in the
`dashboard` namespace.

| Module | In-namespace URL | Cross-namespace URL |
| ------ | ---------------- | ------------------- |
| bus-catcher | `http://bus-catcher-mcp:3001/mcp` | `http://bus-catcher-mcp.dashboard.svc.cluster.local:3001/mcp` |
| fly-over-tracker | `http://fly-over-tracker-mcp:3001/mcp` | `http://fly-over-tracker-mcp.dashboard.svc.cluster.local:3001/mcp` |
| procrastinator-tracker | `http://procrastinator-tracker-mcp:3001/mcp` | `http://procrastinator-tracker-mcp.dashboard.svc.cluster.local:3001/mcp` |
| weather-psychic | `http://weather-psychic-mcp:3001/mcp` | `http://weather-psychic-mcp.dashboard.svc.cluster.local:3001/mcp` |

The agent repository should use the cross-namespace form. The short form is for pods in `dashboard`.

## Runtime commands

| Module | MCP command | Required environment |
| ------ | ----------- | -------------------- |
| bus-catcher | `node dist/index.js --mcp` | `PORT=3000`, `MCP_PORT=3001`, `DB_PATH=/data/bus-catcher.db` |
| fly-over-tracker | `node dist/index.js --mcp` | `HOST=0.0.0.0`, `PORT=3000`, `MCP_PORT=3002`; nginx `host-rewrite` sidecar on 3001 |
| procrastinator-tracker | `sh -c 'node dist/migrate.js && node dist/index.js --mcp'` | `PORT=3000`, `MCP_PORT=3001`, `DATABASE_URL=/data/procrastinator.db` |
| weather-psychic | `node dist/index.js --mcp` | `HOST=0.0.0.0`, `PORT=3000`, `MCP_PORT=3002`; nginx `host-rewrite` sidecar on 3001 |

## Transport contract

- Protocol: MCP streamable HTTP.
- Method: `POST` for JSON-RPC messages.
- Request headers: `Content-Type: application/json` and
  `Accept: application/json, text/event-stream`.
- Path: `/mcp`.
- No MCP-level authentication is implemented. The cluster network boundary is the control.
- The MCP process may also have an HTTP listener environment (`PORT`), but clients must use the MCP
  port and path above.

## Host-header workaround

Fly-over-tracker and weather-psychic use the Hono MCP helper's localhost DNS-rebinding protection.
When the module does not pass a `host` option, the helper defaults to `127.0.0.1` and rejects any
request whose Host header is a Kubernetes Service name, returning `Invalid Host: <service>`.

Each of those pods therefore runs an nginx `host-rewrite` sidecar:

- The MCP process listens on `0.0.0.0:3002`.
- nginx listens on `3001`, proxies to `127.0.0.1:3002`, sets `Host: localhost` and
  `Origin: http://localhost`, disables proxy buffering, and uses long SSE read/send timeouts.
- The Service still targets the sidecar's `mcp-proxy` port 3001. Consumers do not need a custom Host
  header.

Bus-catcher and procrastinator accept the Service DNS Host and have no sidecar. If a consumer or
proxy overwrites the Host header before the sidecar, initialize requests can fail with the same
`Invalid Host` error; keep the normal Service URL.

## Service shape

| Field | Value |
| ----- | ----- |
| Type | `ClusterIP` |
| Selector | `app.kubernetes.io/name=<module>, app.kubernetes.io/component=mcp` |
| Port | `3001` |
| Target port | `3001` |
| External exposure | None: no Ingress, Tailscale host, LoadBalancer, NodePort, or host port |

## Session behavior

The procrastinator MCP server is **single-session per container lifetime**. If its client
disconnects and cannot reconnect:

```bash
kubectl -n dashboard delete pod -l app.kubernetes.io/name=procrastinator-tracker,app.kubernetes.io/component=mcp
```

The ReplicaSet recreates the pod. Task data is on the PVC and survives. The agent should reconnect to
the same Service URL. Bus, fly-over, and weather MCP servers do not carry this caveat in their
documented behavior.

## Cross-namespace smoke test

Use a temporary pod in another namespace, or an existing pod with a shell and `curl`:

```bash
kubectl run mcp-smoke --rm -i --restart=Never --image=curlimages/curl:8.10.1 -- \
  -sS -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}' \
  http://bus-catcher-mcp.dashboard.svc.cluster.local:3001/mcp
```

Expected: an MCP initialize response (JSON or an SSE `data:` frame), not a connection error. Repeat
for the other three URLs.

## Debugging path

Local clients must not require a cluster-exposed MCP endpoint. Use port-forward:

```bash
kubectl -n dashboard port-forward svc/bus-catcher-mcp 3200:3001
# opencode remote MCP URL: http://127.0.0.1:3200/mcp
```

Repeat with ports 3201–3203 for fly-over, procrastinator, and weather. The port-forward is a
debugging session, not a durable deployment.

## Failure contract

| Failure | Expected |
| ------- | -------- |
| MCP pod down | Service has no ready endpoint; client sees connection failure; REST and dashboard continue. |
| MCP container restarted | A new single-session server; client must reconnect. Data on PVC is intact. |
| REST pod down | MCP remains reachable because it has its own Deployment and Service. |
| PVC missing or unwritable | Bus/tasks MCP fails visibly; stateless MCPs continue. |
| Agent namespace changes | Cross-namespace DNS name remains valid; no per-client configuration is needed. |
| MCP image version changed | Pin change in Git; verify initialize/tools and data compatibility before rollout. |
