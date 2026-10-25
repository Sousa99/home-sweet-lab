# 05 — Flux bootstrap

Status: executed and verified on 2026-10-25.

## Current installation

| Item | Current |
| ---- | ------- |
| Flux CLI | `2.9.6` on the development machine |
| Controllers | `source`, `kustomize`, `helm`, `notification`, `image-reflector`, `image-automation` |
| Namespace | `flux-system` |
| Git source | `ssh://git@github.com/Sousa99/home-sweet-lab.git`, branch `main` |
| Sync path | `clusters/dietpi` |
| Deploy key | `flux-home-sweet-lab`, write-enabled |
| Network policies | Disabled (see below) |
| Verified revision | `main@sha1:b3f0e49` |
| Checks | `flux check` passes; source and Kustomization are `Ready` |

## Where Flux runs

| Component | Location | Role |
| --------- | -------- | ---- |
| `flux` CLI | Development machine (Mac) | Bootstrap, reconcile, inspect, debug |
| Flux controllers | DietPi k3s, namespace `flux-system` | Watch Git and reconcile the cluster |
| Git repository | GitHub `Sousa99/home-sweet-lab` | Source of truth |

The DietPi does not need the Flux CLI. The CLI uses the kubeconfig from
[04-kubeconfig-and-lens.md](04-kubeconfig-and-lens.md) to install the controllers and push the
bootstrap manifests. After that, the controllers poll GitHub outbound. No inbound access to the
cluster is required.

## Prerequisites

- Working `kubectl` access to the cluster.
- The `home-sweet-lab` repository exists and is public.
- A write-enabled SSH deploy key on the repository.
- Outbound HTTPS and SSH from DietPi to GitHub and GHCR.

## SSH deploy key

The deployment uses a dedicated SSH key, not a personal access token. The private key stays on the
development machine and is stored in the cluster as the `flux-system` secret.

```bash
ssh-keygen -t ed25519 -C "flux-home-sweet-lab" \
  -f "$HOME/.ssh/home-sweet-lab-flux" -N ""
chmod 600 "$HOME/.ssh/home-sweet-lab-flux"
```

Add `~/.ssh/home-sweet-lab-flux.pub` in GitHub under **Repository → Settings → Deploy keys**, with
**Allow write access** checked.

Write access is required for two write-backs:

1. Bootstrap commits `clusters/dietpi/flux-system/` to `main`.
2. Image automation commits new image tags to `apps/home-assistant/deployment.yaml`.

A read-only key can reconcile but cannot do either. If image automation is ever removed, a
read-only key is sufficient and preferable.

Verify before bootstrap:

```bash
ssh -i "$HOME/.ssh/home-sweet-lab-flux" -o IdentitiesOnly=yes -T git@github.com
```

Expected:

```text
Hi Sousa99/home-sweet-lab! You've successfully authenticated...
```

Do not use a personal SSH key, commit the private key, or add it globally to `~/.ssh/config`.

## Install the Flux CLI

```bash
brew install fluxcd/tap/flux
flux --version
flux check --pre
```

`flux check --pre` must pass before bootstrap.

## Bootstrap

Run from the development machine, not on DietPi:

```bash
flux bootstrap git \
  --url=ssh://git@github.com/Sousa99/home-sweet-lab.git \
  --branch=main \
  --path=clusters/dietpi \
  --private-key-file="$HOME/.ssh/home-sweet-lab-flux" \
  --components-extra=image-reflector-controller,image-automation-controller \
  --network-policy=false
```

Flag notes:

- `--components-extra` installs the image reflector and automation controllers. They are not part of
  the default component set.
- `--network-policy=false` disables Flux's namespace network policies. On this single-node k3s
  installation, kube-router left stale default-deny pod firewall rules after policy changes, which
  blocked controller-to-controller traffic. See [02-k3s.md](02-k3s.md) and
  [09-limitations.md](09-limitations.md).
- The command prompts once to confirm that the deploy key has repository access. If the key is
  already added, pass `--silent` to skip that confirmation.

What the command does:

1. Clones the repository and generates the Flux component manifests.
2. Commits `clusters/dietpi/flux-system/` to `main`.
3. Installs the controllers in `flux-system`.
4. Stores the SSH private key in the `flux-system` secret.
5. Creates the `GitRepository` and root `Kustomization` that reconcile `clusters/dietpi`.

Existing repository content is not replaced.

## Verify

```bash
flux check
flux get sources git -A
flux get kustomizations -A
kubectl -n flux-system get pods
kubectl get crd | grep -i flux
```

Expected:

- All six controllers are `Running`.
- The Git source is `Ready` with a recent revision.
- The root Kustomization is `Ready` and reports `Applied revision`.
- `flux check` ends with `all checks passed`.

On 2026-10-25 the observed state was:

```text
flux-system  gitrepository/flux-system   main@sha1:b3f0e49  False  True
flux-system  kustomization/flux-system   main@sha1:b3f0e49  False  True
```

## Repository layout after bootstrap

```text
clusters/dietpi/
├── flux-system/              # generated; do not hand-edit unless recovering
│   ├── gotk-components.yaml
│   ├── gotk-sync.yaml
│   └── kustomization.yaml
├── infrastructure.yaml       # added in a later phase
└── apps.yaml                 # added in a later phase
```

The root Kustomization recursively reconciles the files in `clusters/dietpi/`.

## Network policy exception

During bootstrap, Flux created three NetworkPolicies in `flux-system`. Deleting them did not remove
the kube-router `KUBE-POD-FW-*` reject rules, and the controllers could not reach each other's
Services. The fix was:

1. Regenerate `gotk-components.yaml` without network policies:
   `flux install --network-policy=false --components-extra=... --export`.
2. Commit and push the change.
3. Reboot the node to flush the stale kube-router rules.

The current `gotk-components.yaml` contains no `NetworkPolicy` objects. Do not re-enable Flux
network policies without testing pod-to-pod and Service traffic first.

## Day-2 operations

```bash
# Force a Git fetch and reconcile.
flux reconcile source git flux-system
flux reconcile kustomization flux-system --with-source

# Inspect.
flux get all -A
flux logs --all-namespaces --follow
flux events --for Kustomization/flux-system

# Trace where an object came from.
flux trace deployment/home-assistant -n home-assistant

# Pause automation during maintenance, then resume.
flux suspend kustomization apps --namespace=flux-system
flux resume kustomization apps --namespace=flux-system
```

Changes are made by committing to Git and letting Flux reconcile. `kubectl apply` is reserved for
bootstrap, manual Secrets, state uploads, and break-glass recovery.

## Deploy key rotation

If the key is lost or compromised:

1. Remove `flux-home-sweet-lab` from GitHub → Settings → Deploy keys.
2. Generate a new key on the development machine.
3. Add the new public key with write access.
4. Delete the cluster secret: `kubectl -n flux-system delete secret flux-system`.
5. Re-run the bootstrap command with the new key and `--silent`.
6. Confirm the source and Kustomization are `Ready`.

The old key must be removed from GitHub and from the cluster. Only the public key was ever added to
GitHub; confirm the private key was never committed.

## Alternative: fine-grained PAT

If SSH is not possible, `flux bootstrap github` works with a PAT. The scopes are broader and the
token lifecycle needs care.

Fine-grained PAT scoped to only `Sousa99/home-sweet-lab`:

| Permission | Access |
| ---------- | ------ |
| Administration | Read and write |
| Contents | Read and write |
| Metadata | Read-only |

Classic PAT: `repo` only. Do not grant `workflow`, `admin:org`, or `delete_repo`.

```bash
export GITHUB_TOKEN="$(gh auth token)"   # or a dedicated PAT

flux bootstrap github \
  --owner=Sousa99 \
  --repository=home-sweet-lab \
  --branch=main \
  --path=clusters/dietpi \
  --personal \
  --private=false \
  --read-write-key \
  --components-extra=image-reflector-controller,image-automation-controller \
  --network-policy=false

unset GITHUB_TOKEN
```

Caveats:

- `--private=false` prevents the existing public repository from being reconfigured as private.
- In deploy-key mode, GitHub deletes the deploy key if the PAT that created it is deleted, and Flux
  warns that PAT expiry can break the key. A short-lived PAT is not maintenance-free.
- With `--token-auth`, the PAT is stored in the cluster and used continuously. That is more
  exposure than the SSH deploy key.

## Recovery

If the Flux installation is lost but the repository is intact, re-run the bootstrap command with the
existing key. Flux reconciles the repository.

If the repository is lost, restore it from the development machine's clone or GitHub's recycle bin
before re-bootstrapping. The cluster does not hold the only copy of the manifests.

If a Kustomization is stuck:

```bash
flux get kustomizations -A
kubectl -n flux-system describe kustomization <name>
kubectl -n flux-system logs deploy/kustomize-controller --tail=100
```

## Uninstall

```bash
flux uninstall --namespace=flux-system
```

This removes Flux and its namespace. It does not delete workloads created by Flux unless they are
also removed. Export state and backups first.

## Troubleshooting

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| Prompt `Please give the key access to your repository` | The deploy key is missing or not yet confirmed | Add the public key as a write-enabled deploy key, or pass `--silent` after verifying |
| `Permission denied (publickey)` | Wrong key, key not added, or wrong repository | Re-run the `ssh -T` check with `IdentitiesOnly=yes` |
| Controllers crash with no logs | Pods cannot reach the Kubernetes API ClusterIP | Check `10.43.0.1:443`, restart k3s, then reboot if pod firewall rules are stale |
| `connect: connection refused` to a Flux Service | Stale kube-router pod firewall rules, or missing Service rules | Disable Flux network policies and reboot; see [02-k3s.md](02-k3s.md) |
| Kustomization stuck in `Reconciliation in progress` | Artifact download or CRD apply failure | Inspect kustomize-controller logs and the Kustomization conditions |
| Image automation cannot push | Deploy key is read-only | Replace it with a write-enabled key and re-bootstrap |
| Repository shows no `flux-system` commit | Wrong URL, branch, or path | Check the bootstrap output and `git log` on `main` |
