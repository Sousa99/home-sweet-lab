# Contract: Dashboard Runtime Configuration

**Scope**: The JSON file served at `/config.json` and its manual Kubernetes Secret.

## Ownership and delivery

| Field | Value |
| ----- | ----- |
| Secret name | `dashboard-config` |
| Namespace | `dashboard` |
| Key | `config.json` |
| Managed by | Operator, not Flux |
| Mount | `/usr/share/nginx/html/config.json` (read-only, `subPath: config.json`) |
| Validator | `apps/dashboard/validate-config.py`, run as the frontend init container |
| Git | Example only; the real file is never committed |

The dashboard image contains a default config. The Secret mount **replaces** that file. Because the
application's loader silently falls back to built-in defaults, the init container must validate the
mounted file before nginx starts.

## Required shape

The file must be a JSON object. Required paths:

- `bus.stops` — array; may be empty, but must be present.
- `flights.location` — object with numeric `lat`, `lng`, and `radiusKm`.
- `weather.location` — object with numeric `latitude`, `longitude`, and non-empty `name` and
  `timezone`.

Other fields are optional and deep-merge over the dashboard defaults. The full field list and ranges
are in [data-model.md](../data-model.md#2-dashboard-config).

## Non-sensitive example

This example is safe to commit and is used by tests. Replace it with the household values in the
Secret. Never commit the real values.

```json
{
  "clock": {
    "defaultFormat": "24h",
    "switchable": false,
    "align": "right"
  },
  "bus": {
    "stops": []
  },
  "flights": {
    "location": { "lat": 0, "lng": 0, "radiusKm": 1 },
    "autoRefresh": 30,
    "maxResults": 5,
    "debugMap": false
  },
  "tasks": {
    "filters": { "finished": false },
    "refreshRateMs": 30000,
    "autoRotateMs": 4000,
    "transitionVariant": "slide-up",
    "slideDurationMs": 750
  },
  "weather": {
    "location": {
      "id": 1,
      "name": "Placeholder",
      "latitude": 0,
      "longitude": 0,
      "timezone": "UTC",
      "country": "Placeholder"
    },
    "refetchIntervalMs": 900000
  },
  "status": { "intervalMs": 30000 },
  "placeholders": []
}
```

A real config typically adds bus stops:

```json
{
  "bus": {
    "stops": [
      { "id": "<stop-id>", "name": "<display-name>", "lines": ["<line>"], "limit": 5 }
    ]
  }
}
```

## Validation rules

The validator must:

1. Reject invalid JSON or a non-object root.
2. Require `bus.stops` to be an array; validate each stop's `id` and `name`, optional `lines`,
   `limit` (1–20), and `refetchIntervalMs` (`>= 0`).
3. Require `flights.location` with finite `lat` (-90–90), `lng` (-180–180), and `radiusKm` (`> 0`).
4. Require `weather.location` with finite `latitude`/`longitude`, non-empty `name` and `timezone`.
5. Validate optional `clock.defaultFormat`/`align`, `tasks` numeric fields, and `status.intervalMs`.
6. Reject unknown value types but allow unknown keys.
7. Never print field values, only the path and reason.
8. Exit `0` on success and non-zero on failure.

Run it locally before creating the Secret:

```bash
python3 apps/dashboard/validate-config.py ~/dashboard-config.json
```

The init container runs the same script against `/config/config.json`.

## Create or update the Secret

```bash
./scripts/create-dashboard-config-secret.sh ~/dashboard-config.json
```

The script creates the `dashboard` namespace if Flux has not yet, validates the file, and creates or
updates the Secret without printing its contents.

To update:

```bash
./scripts/create-dashboard-config-secret.sh ~/dashboard-config.json
kubectl -n dashboard delete pod -l app.kubernetes.io/name=dashboard
kubectl -n dashboard rollout status deployment/dashboard --timeout=5m
```

The Secret is not reconciled by Flux. A cluster rebuild requires recreating it from the operator's
password manager or backup inventory before the frontend can start.

## Failure behavior

| Condition | Result |
| --------- | ------ |
| Secret missing | Frontend pod stays `ContainerCreating`; event names `dashboard-config`. REST/MCP start normally. |
| JSON invalid | Init container exits non-zero; pod restarts with backoff; nginx never serves stale defaults. |
| Required location missing | Init container fails with the missing path. |
| Config changed correctly | Operator deletes the frontend pod; new pod validates and serves the new file. |
| Browser cached old file | `/config.json` is served `no-store`; reload after the pod is Ready. |
| Secret exists but is wrong for the household | The init validator cannot detect wrong-but-valid coordinates. The operator must review the file and keep the real copy out of Git. |

## Privacy rules

- Do not commit the real coordinates, stop IDs, bus line IDs, or timezone if they identify the home.
- Do not put credentials, tokens, or API keys in this file; it is served to browser clients.
- The file is readable by any tailnet client that can reach the dashboard. Tailscale ACLs are the
  access boundary.
- Include the Secret in the operator's backup inventory, but not in public backups or Git.
