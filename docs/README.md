# Documentation

Ordered setup and recovery documentation for the lab. Phase 2 will fill in each document from the
verified state of the existing host.

| Document | Covers | Status |
| -------- | ------ | ------ |
| `01-hardware-and-dietpi.md` | Host hardware, DietPi installation, updates, timezone, SSH | Planned |
| `02-k3s.md` | k3s install, verification, storage class, Traefik, upgrade, uninstall | Planned |
| `03-tailscale.md` | Enrollment, MagicDNS, key expiry, ACLs, status | Planned |
| `04-kubeconfig-and-lens.md` | kubeconfig copy/merge, permissions, Lens import, rotation | Planned |
| `05-flux-bootstrap.md` | Flux CLI, token, bootstrap, verification, recovery | Planned |
| `06-home-assistant.md` | Image, PVC, init containers, ingress, ZBT-2, migration | Planned |
| `07-secrets-and-unsynced-state.md` | Manual secrets, state bundle creation/upload/restore | Planned |
| `08-backups-and-recovery.md` | Backup pull, restore drills, full rebuild | Planned |
| `09-limitations.md` | TLS, single node, Tailscale dependency, storage, discovery | Planned |

## Conventions

- Use placeholders such as `<tailnet>`, `<dietpi-host>`, and `<tailscale-ip>`; never commit real
  identifiers, addresses, or credentials.
- Every procedure states prerequisites, exact commands, verification, and failure behavior.
- Manual steps are marked as manual and linked from the README.
