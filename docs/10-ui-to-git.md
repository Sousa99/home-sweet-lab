# 10 — Promoting UI changes to Git

Status: script implemented and tested on 2026-10-25.

Home Assistant is Git-owned for tracked YAML, but the UI can still change some of those files. This
document covers pulling those changes back into the configuration repository so they can be reviewed
and committed.

## What is Git-owned vs private

| Content | Source of truth | Pulled by this workflow |
| ------- | --------------- | ----------------------- |
| `configuration.yaml` | Git | Yes |
| `automations.yaml`, `scripts.yaml`, `scenes.yaml` | Git | Yes |
| YAML-mode dashboards under `config/dashboards/` | Git | Yes |
| YAML packages under `config/packages/` | Git | Yes |
| Storage-mode dashboards (`.storage/lovelace*`) | PVC | No; use HA backups/state bundles |
| Helpers, integrations, areas, devices, entities | `.storage` | No |
| `secrets.yaml`, `.cloud` | PVC | No; never commit |
| Databases, backups, logs, media, TTS, HACS assets | PVC | No |
| Blueprints | PVC | No; gitignored |

There is no automatic cluster-to-GitHub sync. The script only updates your local checkout; you review
and commit.

## Workflow

1. Make the change in the Home Assistant UI.
2. Pull and review:
   ```bash
   cd ~/Desktop/code/home-sweet-lab
   ./scripts/pull-config.sh
   ```
3. Apply the approved files to the local HA checkout:
   ```bash
   ./scripts/pull-config.sh --apply
   ```
4. Review and commit in `home-sweet-home-home-assistant`:
   ```bash
   cd ~/Desktop/code/home-sweet-home/home-sweet-home-home-assistant
   git diff
   git add config
   git commit -m "chore: sync Home Assistant UI changes"
   git push
   ```
5. The publish workflow builds a new image; Flux updates the Deployment.

**Commit before a pod restart.** The `seed-config` init container re-copies tracked YAML from the
image on every start. UI edits to `automations.yaml`, `scripts.yaml`, `scenes.yaml`, or YAML-mode
dashboards that are not committed will be overwritten at the next restart.

## What the script does

- Pulls top-level `config/*.yaml` except `secrets.yaml` and `*.secret.yaml`.
- Pulls `config/dashboards/**/*.yaml` and `config/packages/**/*.yaml`.
- Uses the running Home Assistant pod, or a temporary helper pod if Home Assistant is stopped.
- Defaults to a dry run with a unified diff.
- `--apply` copies changed and new files into the local checkout.
- Refuses to apply over uncommitted target files unless `--force`.
- Runs `gitleaks` on the staged files when available.
- Never commits or pushes.

Options:

```text
--apply            Copy changed files into the local checkout
--force            Apply even if target files have uncommitted changes
--repo DIR         Home Assistant checkout
--namespace NAME   Home Assistant namespace
-h, --help         Show help
```

## Dashboards

The three current dashboards are storage-mode. They live in `.storage/lovelace*` and are not pulled
into Git. They are covered by Home Assistant backups and state bundles.

YAML-mode dashboards are ordinary YAML files under `config/dashboards/` and are pulled by this
script. To move a storage dashboard into Git, it must first be migrated to YAML mode; that is a
separate, deliberate change.

## Safety rules

- Never commit `.storage`, `secrets.yaml`, `.cloud`, databases, backups, logs, media, TTS, or HACS
  assets.
- Do not put credentials inline in tracked YAML. Use `secrets.yaml` or a manual Kubernetes Secret.
- If `gitleaks` reports a finding, inspect the staged file and remove the credential before applying.
- The state bundle and Home Assistant backups remain the restore path for private state.

## Troubleshooting

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| `No running Home Assistant pod` | HA is scaled down | The script creates a helper pod automatically |
| `Target files have uncommitted changes` | Local edits would be overwritten | Commit/stash them, or use `--force` |
| `No changes` | Cluster matches the checkout | Nothing to commit |
| `Secret scan failed` | A staged YAML contains a credential | Remove it from the source file and re-pull |
| No dashboards pulled | All dashboards are storage-mode | Use HA backups; migrate to YAML mode if needed |
