# 03 — Tailscale

Verified on the current host and cluster on 2026-10-25.

## Current state

| Item | Current |
| ---- | ------- |
| Host client version | `1.104.2` |
| Host service | `tailscaled`, active and enabled |
| Host MagicDNS name | `dietpi.<tailnet>.ts.net` |
| Host Tailscale IP | Assigned and stable; not committed |
| Tailscale SSH (host) | Disabled (`RunSSH: false`) |
| Tailscale Serve (host) | Not used |
| HTTPS certificates | Enabled; the operator issues a certificate for Home Assistant |
| Kubernetes operator | `tailscale-operator` chart `1.104.2`, namespace `tailscale` |
| Ingress proxy | `ts-home-assistant`, tagged `tag:k8s` |
| Home Assistant URL | `https://home-assistant.<tailnet>.ts.net/` |
| Host SSH | Dropbear on port 22 |

The tailnet name and addresses are intentionally omitted. Retrieve them on the host with
`tailscale status` and `tailscale ip -4`; do not paste them into this repository.

## Enroll the host

Install Tailscale after DietPi networking is working:

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --hostname=dietpi
```

Complete the login URL in a browser on a device already in the tailnet. Confirm the host appears
in the admin console and that MagicDNS resolves it.

Tailscale SSH is deliberately left off for v1 so that Dropbear continues to serve `scp`. If
Tailscale SSH is enabled later, confirm that the file-transfer workflow still works before removing
Dropbear.

## Verify

```bash
tailscale version
tailscale status
tailscale ip -4
tailscale netcheck
systemctl is-active tailscaled
systemctl is-enabled tailscaled
```

From the development machine:

```bash
tailscale status | grep -i dietpi
tailscale status | grep -i home-assistant
ping -c 1 dietpi
curl -s -o /dev/null -w '%{http_code}\n' https://home-assistant.<tailnet>.ts.net/
curl -s -o /dev/null -w '%{http_code}\n' http://dietpi/
```

Expected: the Home Assistant URL returns `200`; `http://dietpi/` returns `404` because the root
Traefik route was removed. A connection failure means the operator proxy, Tailscale, or the service
is not reachable.

```bash
kubectl -n home-assistant get ingress
kubectl -n tailscale get pods
```

## Discovery and addressing

- MagicDNS resolves `dietpi` to the host's tailnet address.
- The operator creates a separate device named `home-assistant`, tagged `tag:k8s`, with its own
  tailnet address.
- The k3s API certificate includes the host tailnet address but not the host MagicDNS FQDN. Use the
  address in kubeconfig, or add the FQDN to `tls-san` and restart k3s.
- Tailscale addresses survive reboots and client upgrades. They change if a node is removed from the
  tailnet and re-enrolled. Record current addresses in the operator's password manager, not in Git.

## Access control

The host has no local firewall. Tailscale ACLs are the primary remote-access boundary. Restrict at
least:

- Host SSH (22) to the operator's devices.
- Kubernetes API (6443) to the development machine.
- Home Assistant (`tag:k8s` port 443) to household members.

The operator needs two tags:

- `tag:k8s-operator`: the operator and its OAuth client.
- `tag:k8s`: the ingress/egress proxies and services the operator creates.

Merge this into the tailnet policy (do not replace existing rules):

```json
{
  "tagOwners": {
    "tag:k8s-operator": ["autogroup:admin"],
    "tag:k8s": ["tag:k8s-operator"]
  },
  "autoApprovers": {
    "services": {
      "tag:k8s": ["tag:k8s"]
    }
  },
  "grants": [
    {
      "src": ["autogroup:member"],
      "dst": ["tag:k8s"],
      "ip": ["tcp:80", "tcp:443"]
    }
  ]
}
```

If the policy uses `acls` instead of `grants`, use the equivalent ACL:

```json
{ "action": "accept", "src": ["autogroup:member"], "dst": ["tag:k8s:80,443"] }
```

Do not expose SSH or the Kubernetes API to the public internet.

## Kubernetes operator and HTTPS

Home Assistant is exposed by the Tailscale Kubernetes Operator, not by Traefik. The operator is
managed by Flux:

- HelmRelease `tailscale-operator` in `flux-system`, chart `1.104.2`, target namespace `tailscale`.
- OAuth client `home-sweet-lab-operator` with **Services**, **Devices → Core**, and
  **Auth Keys** read/write, tagged `tag:k8s-operator`.
- The OAuth client ID and secret are stored in the manual `operator-oauth` Secret in the `tailscale`
  namespace. They are never committed.

The Ingress is:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: home-assistant
  namespace: home-assistant
spec:
  ingressClassName: tailscale
  defaultBackend:
    service:
      name: home-assistant
      port:
        number: 8123
  tls:
    - hosts:
        - home-assistant
```

The operator creates `home-assistant.<tailnet>.ts.net`, obtains a Tailscale-issued certificate, and
proxies traffic to the Home Assistant Service. The host's Traefik no longer serves Home Assistant;
`/` is available for a future landing page.

Certificate renewal is automatic. If the OAuth client is rotated, update the `operator-oauth` Secret
and restart the operator pod. If the operator is removed, Home Assistant keeps running but the
hostname becomes unavailable.

## Key expiry

A server that loses its key cannot be reached remotely until it is re-authenticated at the console.
Disable key expiry for the lab host in the Tailscale admin console, or set a long expiry and record
the renewal date. Tagged operator proxy devices are managed by the operator. Disabling expiry
increases the impact of a stolen device key; protect the host and use tailnet ACLs accordingly.

## Failure behavior

| Failure | Effect |
| ------- | ------ |
| Tailscale coordination unreachable | Remote access fails; local cluster and LAN access continue |
| Host `tailscaled` stopped | SSH and kubeconfig access over the tailnet fail; the operator proxy may remain reachable because it is a separate device |
| Operator or proxy down | `https://home-assistant.<tailnet>.ts.net/` is unavailable; the Home Assistant pod and automations keep running |
| Certificate issuance fails | HTTPS fails; inspect `kubectl -n tailscale logs` and the tailnet HTTPS setting |
| Tailnet ACL changes | Access is denied even though the proxy is healthy |
| Node removed and re-enrolled | Tailnet addresses may change; update `tls-san`, kubeconfig, and DNS expectations |

Tailscale is an intentional cloud dependency for coordination, remote access, and certificates.
Zigbee control, automations, and local Home Assistant operation do not depend on it.

## Never commit

- Tailnet name, tailnet ID, or MagicDNS FQDN.
- Tailscale IP addresses.
- Auth keys, OAuth client secrets, node keys, or `tailscale up` login URLs.
- Admin console screenshots that show device names or users.
