# Documentation

Ordered setup and recovery documentation for the lab. Documents 01–11 describe the verified and
deployed state. Document 12 adds the MQTT one-device path and awaits the first GHCR image, the Home
Assistant MQTT integration, and a maintenance-window node reboot. The destructive full-rebuild
drills remain a maintenance-window task.

| Document | Covers | Status |
| -------- | ------ | ------ |
| `01-hardware-and-dietpi.md` | Host hardware, DietPi installation, updates, timezone, SSH | Verified |
| `02-k3s.md` | k3s install, verification, storage class, Traefik, upgrade, uninstall | Verified |
| `03-tailscale.md` | Enrollment, MagicDNS, key expiry, ACLs, operator, HTTPS | Verified; operator and HTTPS enabled |
| `04-kubeconfig-and-lens.md` | kubeconfig copy/merge, permissions, Lens import, rotation | Verified |
| `05-flux-bootstrap.md` | Flux CLI, SSH deploy key, bootstrap, verification, recovery | Executed 2026-10-25; verified |
| `06-home-assistant.md` | Image, PVC, init containers, Tailscale Ingress, ZBT-2, migration | Deployed 2026-10-25; verified |
| `07-secrets-and-unsynced-state.md` | Manual secrets, state bundle creation/upload/restore | Scripts implemented; migration exercised |
| `08-backups-and-recovery.md` | Backup pull, restore drills, full rebuild | Pull/restore drills executed 2026-10-25; full rebuild pending |
| `09-limitations.md` | Access, single node, Tailscale dependency, storage, discovery | Verified |
| `10-ui-to-git.md` | Reverse-sync UI YAML changes for review and commit | Script tested 2026-10-25 |
| `11-host-metrics.md` | HTTP exporter, metric contract, legacy Scrape UI, recovery | Deployed; legacy Scrape reference |
| `12-host-metrics-mqtt.md` | MQTT broker, one-device discovery, HA MQTT UI, migration, recovery | Implemented; image/HA verification pending |

Host-specific notes and the ZBT-2 udev rule live in [`../host/dietpi/`](../host/dietpi/).

## Conventions

- Use placeholders such as `<tailnet>`, `<dietpi-host>`, and `<tailscale-ip>`; never commit real
  identifiers, addresses, or credentials.
- Every procedure states prerequisites, exact commands, verification, and failure behavior.
- Manual steps are marked as manual and linked from the README.
