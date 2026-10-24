# 01 — Hardware and DietPi

Verified on the current lab host on 2026-10-24. Values marked **current** are observations, not
requirements; replace them when rebuilding.

## Current hardware and OS

| Item | Current |
| ---- | ------- |
| Role | Single k3s control-plane node |
| Hostname | `DietPi` |
| Operating system | DietPi 10.8.2 on Debian GNU/Linux 13.7 (trixie) |
| Kernel | `6.12.113+deb13-amd64` (x86-64) |
| CPU | 8 vCPU |
| Memory | 15 GiB |
| Root disk | 939 GB NVMe, ext4, `noatime,lazytime`, 888 GB free |
| Login user | `dietpi` (UID 1000), passwordless `sudo` |
| SSH | Dropbear on port 22, active and enabled |
| Firewall | None installed (`ufw` and `nft` absent) |
| Timezone | UTC as observed; `Europe/Lisbon` data is available |

The host is an old x86-64 PC. There is no hardware RAID, no uninterruptible power supply, and no
out-of-band management. Treat the node as a single point of failure.

## First boot

1. Flash the DietPi image for x86-64 to the system disk.
2. Boot the PC with a monitor and keyboard for the first run.
3. In `dietpi-config`, set:
   - hostname `DietPi`
   - user `dietpi`
   - SSH server: Dropbear (the DietPi default)
   - timezone `Europe/Lisbon`
   - locale `C.UTF-8` unless a different locale is required
4. Reboot and confirm the host is reachable.

```bash
hostname
cat /etc/os-release | head -3
uname -a
nproc
free -h
df -h /
```

## Updates

```bash
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

Reconnect after the reboot and confirm k3s and Tailscale return automatically. DietPi's own updater
is optional; keep the Debian security updates current.

## Timezone

The current host reports UTC. Home Assistant runs with `TZ=Europe/Lisbon`, but the host clock should
also use the household timezone so logs and k3s events agree:

```bash
sudo timedatectl set-timezone Europe/Lisbon
timedatectl
```

If `timedatectl` reports that NTP is unavailable, enable it:

```bash
sudo timedatectl set-ntp true
```

## SSH access

Dropbear is already running. The `dietpi` user has passwordless `sudo`, so administrative commands
work without a separate root login.

```bash
# From the development machine; use the tailnet name or address.
ssh dietpi@dietpi

# Verify passwordless sudo.
sudo -n true && echo "sudo ok"
```

Recommended key-based access:

```bash
ssh-keygen -t ed25519 -C "home-sweet-lab"
ssh-copy-id dietpi@dietpi
ssh dietpi@dietpi
```

After confirming key authentication, disable password logins. With DietPi's Dropbear setup, set the
option in `/boot/dietpi.txt` and apply it through `dietpi-config`, or add `-s` to
`DROPBEAR_EXTRA_ARGS` in `/etc/default/dropbear` and restart Dropbear:

```bash
sudo systemctl restart dropbear
```

Do not expose SSH to the public internet. Tailscale is the intended access path.

## Security posture

The current host has no firewall. Dropbear listens on `0.0.0.0:22` and the k3s API listens on
`*:6443`, so both are reachable from the local network as well as the tailnet.

For v1, Tailscale ACLs and the household network are the control boundary. If the host is placed on
an untrusted network, add a host firewall that allows SSH and the API only from the tailnet
interface, and keep the LAN path closed.

## Disk and storage

The root filesystem is ext4 on NVMe. Kubernetes persistent volumes are directories under
`/var/lib/rancher/k3s/storage/`, managed by the `local-path` provisioner.

```bash
df -h / /var/lib/rancher/k3s/storage
sudo ls -la /var/lib/rancher/k3s/storage
```

There is no separate data disk, no snapshot facility, and no replication. Home Assistant backups on
the volume are the recovery mechanism; see [08-backups-and-recovery.md](08-backups-and-recovery.md).

## What is not managed by this document

- BIOS/firmware settings and boot order.
- Disk encryption. If the PC leaves the household, encrypt the disk.
- UPS and power-loss behavior.
- Hardware replacement.

Document any change to these in this file and record the date.
