# Home Sweet Lab Repository Guidance

This repository is configuration-as-code for the household lab: one k3s node on DietPi,
reconciled by Flux, with Home Assistant as the first workload.

## Rules

- Read `.specify/memory/constitution.md` before making changes.
- Never commit secrets, tokens, private keys, kubeconfigs, state bundles, or backup archives.
- Never commit real Tailscale IPs, MagicDNS names, or tailnet identifiers; use placeholders.
- Keep cluster and workload changes reviewable and documented.
- Validate manifests and Kustomizations before reconciling.
- Test affected workloads and recovery paths on the real cluster.
- Home Assistant configuration is owned by `home-sweet-home-home-assistant`; this repository owns
  its image deployment and cluster resources.
- Keep LLM, MCP, and conversation orchestration in `home-sweet-home-agent`.

## Change workflow

1. Describe the cluster, workload, or access behavior being changed.
2. Update manifests and documentation together.
3. Run the validation checks (`scripts/validate.sh` once available).
4. Reconcile with Flux and verify normal, unavailable, and recovery behavior.
5. Record hardware-specific setup, manual UI steps, and anything that lives outside Git.

## Repository boundaries

- `clusters/` is the Flux entry point; bootstrap owns `clusters/dietpi/flux-system/`.
- `infrastructure/` holds cluster-wide resources.
- `apps/` holds workloads; each app is a self-contained Kustomization.
- `docs/` holds setup and recovery procedures.
- `host/` holds host-specific notes and udev rules that must be applied manually.
- `scripts/` holds operational helpers; they must be safe to re-run.

## Secrets and unsynced state

Manual by design for v1: `.storage`, databases, `secrets.yaml`, backups, and state bundles.
Never add them to Git. Document each manual copy in the relevant phase document.

## Validation

Until `scripts/validate.sh` lands, use:

```bash
kubectl kustomize apps/home-assistant
kubeconform -strict -summary apps/home-assistant
```
