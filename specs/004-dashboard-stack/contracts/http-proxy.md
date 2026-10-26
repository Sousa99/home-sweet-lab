# Contract: Frontend HTTP Proxy and Access

**Scope**: Browser-to-dashboard traffic, same-origin API proxy, health paths, and exposure rules.

## Public origin

| Field | Value |
| ----- | ----- |
| Origin | `https://dashboard.<tailnet>.ts.net/` |
| Exposure | Tailscale Ingress only |
| Backend | `dashboard` Service, port 80, nginx |
| TLS | Tailscale-issued certificate |
| Traefik | Not used |
| Public internet | Not exposed |

The frontend is the only externally reachable dashboard component. REST and MCP Services are
ClusterIP only.

## Static routes

| Request | Result |
| ------- | ------ |
| `GET /` | SPA `index.html`; client-side routes fall back to `index.html` |
| `GET /assets/...` | Static frontend assets |
| `GET /config.json` | Runtime JSON from the `dashboard-config` Secret |
| `GET /mcp` | `404`; MCP is not proxied |

`/config.json` is served with `Cache-Control: no-store` so a pod restart plus browser reload picks
up a new config.

## API proxy routes

The published widgets receive a same-origin `baseUrl` such as `/api/bus` and append module paths.
The nginx proxy strips `/api/<module>` and forwards the remainder.

| Public route prefix | Upstream Service | Upstream port | Prefix rewrite | Example |
| ------------------- | ---------------- | ------------- | -------------- | ------- |
| `/api/bus/` | `bus-catcher-rest` | 3000 | strip `/api/bus` | `/api/bus/api/health` → `/api/health` |
| `/api/tasks/` | `procrastinator-tracker-rest` | 3000 | strip `/api/tasks` | `/api/tasks/health` → `/health` |
| `/api/fly/` | `fly-over-tracker-rest` | 3000 | strip `/api/fly` | `/api/fly/api/fly-overs` → `/api/fly-overs` |
| `/api/weather/` | `weather-psychic-rest` | 3000 | strip `/api/weather` | `/api/weather/api/health` → `/api/health` |

Required proxy behavior:

- Resolve upstreams with Kubernetes DNS. Do not use Docker's `127.0.0.11`.
- Forward the HTTP method, body, query string, and relevant headers.
- Set `Host`, `X-Real-IP`, `X-Forwarded-For`, and `X-Forwarded-Proto`.
- No CORS headers are required because the browser uses the dashboard origin.
- Use a 5-second connect timeout and a 60-second read/send timeout.
- If an upstream is down, return `502`/`504`; the dashboard's status strip and block handle the
  failure.

## Documented health and smoke paths

| Path | Expected |
| ---- | -------- |
| `GET /api/bus/api/health` | `200` when bus REST is ready |
| `GET /api/tasks/health` | `200` when tasks REST is ready |
| `GET /api/fly/api/fly-overs?lat=<lat>&lng=<lng>&radiusKm=<km>` | `2xx` when fly REST is reachable; may depend on the external feed |
| `GET /api/weather/api/health` | `200` when weather REST is ready |
| `POST /api/bus/api/refresh` | Starts the one-off GTFS ingest; may take minutes |
| `GET /api/bus/api/stops/<stop-id>/times` | Departures for a configured stop |

## Frontend Ingress

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: dashboard
  namespace: dashboard
spec:
  ingressClassName: tailscale
  defaultBackend:
    service:
      name: dashboard
      port:
        number: 80
  tls:
    - hosts:
        - dashboard
```

The operator creates the `dashboard` proxy device and
`https://dashboard.<tailnet>.ts.net/`. The repository commits only the short hostname `dashboard`,
never the tailnet FQDN.

## Local verification

```bash
kubectl -n dashboard port-forward svc/dashboard 8080:80
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/
curl -sS http://127.0.0.1:8080/config.json | python3 -m json.tool >/dev/null
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/api/bus/api/health
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/api/tasks/health
curl -sS -o /dev/null -w '%{http_code}\n' 'http://127.0.0.1:8080/api/fly/api/fly-overs?lat=0&lng=0&radiusKm=1'
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8080/api/weather/api/health
```

Expected: the page and config return `200`; each backend health call returns a non-5xx response while
the corresponding pod is Ready.

## Failure contract

| Failure | Browser behavior |
| ------- | ---------------- |
| One REST pod down | The dashboard shell loads; that block and status indicator show unavailable; other blocks continue. |
| Frontend config missing | Pod does not start; Tailscale URL is unavailable; `kubectl describe pod` names the missing Secret. |
| Frontend config invalid | Init container fails; the old frontend pod may still serve during a rollout; the new pod reports the validation path. |
| Tailscale operator or ACL down | The URL is unreachable; cluster-internal MCP and REST continue. |
| Upstream Service recreated with a new ClusterIP | Restart the frontend pod so nginx re-resolves the static upstream names. |
