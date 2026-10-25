# Documentation

Ordered setup and recovery documentation for the lab. Documents 01–07 describe the verified,
executed state. Document 08 remains the next phase.

| Document | Covers | Status |
| -------- | ------ | ------ |
| `01-hardware-and-dietpi.md` | Host hardware, DietPi installation, updates, timezone, SSH | Verified |
| `02-k3s.md` | k3s install, verification, storage class, Traefik, upgrade, uninstall | Verified |
| `03-tailscale.md` | Enrollment, MagicDNS, key expiry, ACLs, status | Verified |
| `04-kubeconfig-and-lens.md` | kubeconfig copy/merge, permissions, Lens import, rotation | Verified |
| `05-flux-bootstrap.md` | Flux CLI, SSH deploy key, bootstrap, verification, recovery | Executed 2026-10-25; verified |
| `06-home-assistant.md` | Image, PVC, init containers, ingress, ZBT-2, migration | Deployed 2026-10-25; verified |
| `07-secrets-and-unsynced-state.md` | Manual secrets, state bundle creation/upload/restore | Scripts implemented; migration exercised |
| `08-backups-and-recovery.md` | Backup pull, restore drills, full rebuild | Documented; drills pending |
| `09-limitations.md` | TLS, single node, Tailscale dependency, storage, discovery | Verified |

Host-specific notes and the ZBT-2 udev rule live in [`../host/dietpi/`](../host/dietpi/).

## Conventions

- Use placeholders such as `<tailnet>`, `<dietpi-host>`, and `<tailscale-ip>`; never commit real
  identifiers, addresses, or credentials.
- Every procedure states prerequisites, exact commands, verification, and failure behavior.
- Manual steps are marked as manual and linked from the README.
