# 03 — Tailscale

Verified on the current host on 2026-10-24.

## Current state

| Item | Current |
| ---- | ------- |
| Client version | `1.104.2` |
| Service | `tailscaled`, active and enabled |
| MagicDNS name | `dietpi.<tailnet>.ts.net` |
| Tailscale IP | Assigned and stable; not committed |
| Tailscale SSH | Disabled (`RunSSH: false`) |
| Tailscale Serve | Not configured |
| HTTPS certificates | Not enabled |
| Host SSH | Dropbear on port 22 |

The tailnet name and address are intentionally omitted. Retrieve them on the host with
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
ping -c 1 dietpi
curl -I http://dietpi/
```

The `curl` returns `404` from Traefik until an ingress route exists. A connection failure means
Traefik or Tailscale is not reachable, not that Home Assistant is down.

## Discovery and addressing

- MagicDNS resolves `dietpi` to the host's tailnet address.
- The k3s API certificate includes the tailnet address but not the MagicDNS FQDN. Use the address
  in kubeconfig, or add the FQDN to `tls-san` and restart k3s.
- Tailscale addresses survive reboots and client upgrades. They change if the node is removed from
  the tailnet and re-enrolled. Record the current address in the operator's password manager, not
  in Git.

## Access control

The current host has no local firewall. Tailscale ACLs are the primary remote-access boundary.
Restrict at least:

- SSH (22) to the operator's devices.
- Kubernetes API (6443) to the development machine.
- Traefik (80/443) to household devices.

A minimal policy shape (replace tags and users with the real tailnet values, and keep it out of
Git if it contains identities):

```json
{
  "tagOwners": {
    "tag:lab": ["autogroup:admin"]
  },
  "acls": [
    { "action": "accept", "src": ["autogroup:admin"], "dst": ["tag:lab:22,6443,80,443"] },
    { "action": "accept", "src": ["autogroup:member"], "dst": ["tag:lab:80,443"] }
  ]
}
```

Do not expose SSH or the Kubernetes API to the public internet as a workaround for a broken ACL.

## Key expiry

A server that loses its key cannot be reached remotely until it is re-authenticated at the console.
Disable key expiry for the lab node in the Tailscale admin console, or set a long expiry and record
the renewal date. Disabling expiry increases the impact of a stolen device key; protect the host and
use tailnet ACLs accordingly.

## HTTPS and Tailscale Serve are deferred

The current design serves Home Assistant over HTTP on the tailnet. WireGuard encrypts traffic in
transit, but the browser does not see a secure context.

Do not enable Tailscale Serve on port 443 while the Traefik service load balancer holds 443. Choose
one of:

1. Move Traefik to port 80 only, then front it with Tailscale Serve on 443.
2. Adopt the Tailscale Kubernetes Operator and expose the Service directly.
3. Add cert-manager and a publicly trusted certificate with DNS validation.

All three are future work; see [09-limitations.md](09-limitations.md).

## Failure behavior

| Failure | Effect |
| ------- | ------ |
| Tailscale coordination unreachable | Remote access fails; local cluster and LAN access continue |
| Tailscale client stopped | Tailnet address disappears from peers; local traffic continues |
| Node removed and re-enrolled | Tailnet address may change; update `tls-san`, kubeconfig, and ingress expectations |
| Tailscale SSH enabled without checking scp | File transfers may break; keep Dropbear until verified |

Tailscale is an intentional cloud dependency for coordination and remote access. Zigbee control,
automations, and local Home Assistant operation do not depend on it.

## Never commit

- Tailnet name, tailnet ID, or MagicDNS FQDN.
- Tailscale IP addresses.
- Auth keys, node keys, or `tailscale up` login URLs.
- Admin console screenshots that show device names or users.
