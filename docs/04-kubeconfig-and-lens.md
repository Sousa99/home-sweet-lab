# 04 — kubeconfig and Lens

Verified on the development machine on 2026-10-24.

## Current state

| Item | Current |
| ---- | ------- |
| kubeconfig | `~/.kube/config` |
| Context | `default` (recommended rename: `dietpi`) |
| Cluster | `default` |
| User | `default` |
| API server | `https://<dietpi-tailscale-ip>:6443` |
| kubectl client | `v1.37.1` |
| Kustomize | `v5.8.1` |
| Lens | `2026.10.121159-latest` |

The kubeconfig is a cluster-admin credential. It is not a deployment artifact and must never be
committed.

## Copy the kubeconfig from DietPi

k3s writes the admin kubeconfig to `/etc/rancher/k3s/k3s.yaml` with root-only permissions. Its
server field points at `127.0.0.1`, which only works on the host. Rewrite it to the Tailscale
address before copying.

On DietPi:

```bash
sudo cp /etc/rancher/k3s/k3s.yaml /home/dietpi/k3s.yaml
sudo chown dietpi:dietpi /home/dietpi/k3s.yaml
chmod 600 /home/dietpi/k3s.yaml

# Replace the loopback address with the host's tailnet address.
sed -i 's/127\.0\.0\.1/<dietpi-tailscale-ip>/' /home/dietpi/k3s.yaml
grep 'server:' /home/dietpi/k3s.yaml
```

From the development machine:

```bash
mkdir -p ~/.kube
scp dietpi@dietpi:/home/dietpi/k3s.yaml ~/.kube/dietpi.yaml
chmod 600 ~/.kube/dietpi.yaml
```

`dietpi@dietpi` means the `dietpi` user at the MagicDNS hostname. If MagicDNS is unavailable, use
`dietpi@<dietpi-tailscale-ip>`.

Remove the staging copy from the host:

```bash
rm /home/dietpi/k3s.yaml
```

### Alternative without a staging copy

The `dietpi` user has passwordless sudo, so the file can be streamed directly:

```bash
ssh dietpi@dietpi 'sudo cat /etc/rancher/k3s/k3s.yaml' > ~/.kube/dietpi.yaml
chmod 600 ~/.kube/dietpi.yaml
sed -i '' 's/127\.0\.0\.1/<dietpi-tailscale-ip>/' ~/.kube/dietpi.yaml
```

The `sed -i ''` form is macOS. On Linux, use `sed -i`.

## Merge into the existing kubeconfig

Rename the context, cluster, and user first so they cannot collide with an existing kubeconfig:

```bash
KUBECONFIG=~/.kube/dietpi.yaml kubectl config rename-context default dietpi
KUBECONFIG=~/.kube/dietpi.yaml kubectl config rename-cluster default dietpi
KUBECONFIG=~/.kube/dietpi.yaml kubectl config rename-user default dietpi-admin
```

Then merge without losing an existing configuration:

```bash
if [ -f ~/.kube/config ]; then
  cp ~/.kube/config "$HOME/.kube/config.bak.$(date +%Y%m%d-%H%M%S)"
  KUBECONFIG=~/.kube/config:~/.kube/dietpi.yaml \
    kubectl config view --flatten > ~/.kube/config.merged
  mv ~/.kube/config.merged ~/.kube/config
else
  mv ~/.kube/dietpi.yaml ~/.kube/config
fi
chmod 600 ~/.kube/config
```

If `kubectl config view` reports duplicate names, rename the cluster and user in the incoming file
as well:

```bash
KUBECONFIG=~/.kube/dietpi.yaml kubectl config rename-cluster default dietpi
KUBECONFIG=~/.kube/dietpi.yaml kubectl config rename-user default dietpi-admin
```

## Verify

```bash
kubectl config get-contexts
kubectl config use-context dietpi
kubectl cluster-info
kubectl get nodes -o wide
kubectl get pods -A
```

Expected: context `dietpi`, node `dietpi` is `Ready`, and the kube-system pods are running.

## Lens

1. Open Lens.
2. Choose **File → Add Cluster** (or the plus button in the cluster list).
3. Paste the contents of `~/.kube/config`, or select the file.
4. Name the cluster `home-sweet-lab` or `dietpi`.
5. Open the cluster and confirm the node and namespaces are visible.

Lens is for observation and troubleshooting. It is not the deployment mechanism; Flux owns the
cluster state. Do not use Lens to make long-lived manual changes.

Lens workspace data can contain cluster credentials. Keep it out of Git.

## Security

- `chmod 600` the kubeconfig and every copy.
- Never commit, email, paste into a ticket, or store in a public note.
- Prefer one kubeconfig per cluster and select with `KUBECONFIG` or `kubectl config use-context`.
- For day-to-day use, consider creating a least-privilege ServiceAccount instead of sharing the
  cluster-admin kubeconfig.
- If the file leaks, rotate the k3s serving and client certificates and re-copy the kubeconfig:

  ```bash
  sudo k3s certificate rotate
  sudo systemctl restart k3s
  ```

  Confirm the cluster is healthy, then replace the development machine's kubeconfig. Treat the old
  file as compromised even if rotation succeeds.

## Troubleshooting

| Symptom | Cause | Fix |
| ------- | ----- | --- |
| `x509: certificate is valid for ... not ...` | Server name is not in the certificate SANs | Use the Tailscale IP, or add the FQDN to `tls-san` and restart k3s |
| `connection refused` | Tailscale down, k3s down, or wrong address | Check `tailscale status`, `systemctl status k3s`, and the server field |
| `Unauthorized` | Stale client certificate after rotation | Re-copy the kubeconfig from `/etc/rancher/k3s/k3s.yaml` |
| `scp: dest open ... Permission denied` | `k3s.yaml` is root-only | Copy to `/home/dietpi` with `sudo` first |
| `REMOTE HOST IDENTIFICATION HAS CHANGED` | Host reinstalled with new SSH keys | Remove the stale entry from `known_hosts` after verifying the host |
| Duplicate context/cluster names after merge | Existing kubeconfig uses the same names | Rename the incoming context, cluster, and user before merging |
| Lens cannot connect | kubeconfig still points at `127.0.0.1` | Rewrite the server field to the tailnet address |

## What not to do

- Do not commit `~/.kube/config` or any `.kube` directory.
- Do not expose the API server on the public internet.
- Do not disable certificate verification with `insecure-skip-tls-verify`; fix the SAN instead.
