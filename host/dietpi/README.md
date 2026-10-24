# DietPi host notes

Host-specific facts and manual steps that cannot be delivered by Flux. Every command runs on the
DietPi host as the `dietpi` user.

## Verified state

| Item | Value |
| ---- | ----- |
| Hostname | `DietPi` |
| OS | DietPi 10.8.2, Debian 13.7 (trixie) |
| Kernel | `6.12.113+deb13-amd64` |
| CPU / RAM | 8 vCPU / 15 GiB |
| Root disk | 939 GB NVMe, ext4, 888 GB free |
| SSH | Dropbear on port 22, password authentication enabled |
| sudo | `dietpi` has passwordless sudo |
| Firewall | None installed |
| k3s | `v1.36.5+k3s1`, active and enabled |
| Tailscale | `1.104.2`, active and enabled |
| ZBT-2 | `303a:831a`, `cdc_acm`, `/dev/ttyACM0`, by-id path present |

The tailnet name, tailnet address, node token, and kubeconfig are intentionally not recorded here.

## SSH key setup

```bash
# From the development machine
ssh-keygen -t ed25519 -C "home-sweet-lab"
ssh-copy-id dietpi@dietpi
ssh dietpi@dietpi
```

After key authentication works, disable password logins. DietPi uses Dropbear; set
`SOFTWARE_DISABLE_SSH_PASSWORD_LOGINS=1` in `/boot/dietpi.txt` and apply it with `dietpi-config`, or
add `-s` to `DROPBEAR_EXTRA_ARGS` in `/etc/default/dropbear` and restart Dropbear.

## Timezone

The host currently reports UTC. Set the household timezone:

```bash
sudo timedatectl set-timezone Europe/Lisbon
timedatectl
```

## ZBT-2 serial device

The device is already attached. Confirm the stable path:

```bash
ls -l /dev/serial/by-id/
udevadm info -q property -n /dev/ttyACM0 | \
  grep -E 'ID_VENDOR_ID|ID_MODEL_ID|ID_SERIAL_SHORT'
```

Install the stable symlink rule:

```bash
sudo install -m 0644 udev/99-zbt2.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=tty
ls -l /dev/zbt2
```

Expected: `/dev/zbt2` points at the ZBT-2 device, group `dialout`, mode `0660`.

Do not commit the full serial number or the exact by-id filename. Use `<serial>` in documentation
and manifests.

## Firewall note

There is no host firewall. Dropbear (22) and the k3s API (6443) listen on all interfaces. Tailscale
ACLs are the control boundary. If the host is exposed to an untrusted network, add a firewall that
allows only the tailnet interface before treating the setup as safe.

## What must stay manual

- udev rule installation.
- Host timezone and updates.
- SSH key and password policy.
- Any future firewall rules.
- Physical device connections.

Record changes here and in the phase document that depends on them.
